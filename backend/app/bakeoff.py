"""Parallel agent bakeoff: same prompt, different AgentConfigs, compare outcomes.

Reuses fork/split (`apply_forward_routes`) and per-stage AgentConfig (model, tools,
prompt, temperature). Metadata lives on handoff JSON — no schema migration.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import AgentConfig, AgentRun, Board, Card, Stage, StageTransition
from .orchestrator.enqueue import enqueue_stage_run
from .orchestrator.progression import Route
from .orchestrator.split import apply_forward_routes, load_family_cards
from .orchestrator.state_machine import CardStatus
from .token_usage import add_usage, empty_usage, usage_from_handoff
from .utc import utc_now

SETTLED = {CardStatus.DONE, CardStatus.WAITING_APPROVAL, CardStatus.WAITING_TOOL_APPROVAL, CardStatus.BLOCKED}
ACTIVE = {CardStatus.RUNNING, CardStatus.WAITING_JOIN}


class BakeoffError(ValueError):
    """Invalid bakeoff request."""


def _arm_label(raw: str | None, index: int) -> str:
    text = str(raw or "").strip()
    if text:
        return text[:64]
    return chr(ord("A") + index) if index < 26 else f"Arm {index + 1}"


def _normalize_arm(raw: dict[str, Any], index: int) -> dict[str, Any]:
    label = _arm_label(raw.get("label") if isinstance(raw, dict) else None, index)
    tools = raw.get("tool_allowlist") if isinstance(raw, dict) else None
    if not isinstance(tools, list):
        tools = []
    allowlist = [str(item).strip() for item in tools if str(item).strip()]
    prompt = raw.get("system_prompt") if isinstance(raw, dict) else None
    model = raw.get("model") if isinstance(raw, dict) else None
    provider = raw.get("llm_provider") if isinstance(raw, dict) else None
    temperature = raw.get("temperature") if isinstance(raw, dict) else None
    return {
        "label": label,
        "system_prompt": (
            str(prompt).strip()
            if isinstance(prompt, str) and prompt.strip()
            else (
                f"You are bakeoff arm {label}. Solve the same task as the other arms. "
                "Produce a concise handoff with summary and DECISION: approve or reject."
            )
        ),
        "model": str(model).strip() if isinstance(model, str) and model.strip() else "",
        "llm_provider": str(provider).strip() if isinstance(provider, str) else "",
        "temperature": float(temperature) if isinstance(temperature, (int, float)) else 0.2,
        "tool_allowlist": allowlist,
        "workspace_path": str(raw.get("workspace_path") or "") if isinstance(raw, dict) else "",
        "git_url": str(raw.get("git_url") or "") if isinstance(raw, dict) else "",
    }


def _bakeoff_meta(handoff: Any) -> dict[str, Any] | None:
    if not isinstance(handoff, dict):
        return None
    raw = handoff.get("bakeoff")
    return raw if isinstance(raw, dict) and raw.get("id") else None


def _latest_run(card: Card) -> AgentRun | None:
    runs = list(card.runs or [])
    if not runs:
        return None
    return max(runs, key=lambda run: run.created_at or utc_now())


def _latest_work_run(card: Card, arm_stage_id: str | None = None) -> AgentRun | None:
    """Prefer a real stage run over the synthetic split/fork seed."""
    runs = list(card.runs or [])
    if not runs:
        return None

    def is_seed(run: AgentRun) -> bool:
        inputs = run.inputs if isinstance(run.inputs, dict) else {}
        return bool(inputs.get("split_plan") or inputs.get("forked_from") or inputs.get("bakeoff_seed"))

    candidates = [run for run in runs if not is_seed(run)]
    if arm_stage_id:
        staged = [run for run in candidates if run.stage_id == arm_stage_id]
        if staged:
            candidates = staged
    if not candidates:
        candidates = runs
    return max(candidates, key=lambda run: run.created_at or utc_now())


def _find_bakeoff_id(family: list[Card]) -> str | None:
    for card in family:
        for run in card.runs or []:
            meta = _bakeoff_meta(run.handoff)
            if meta:
                return str(meta["id"])
    return None


def _arm_rows_for_id(family: list[Card], bakeoff_id: str, stages_by_id: dict[str, Stage]) -> list[dict[str, Any]]:
    by_label: dict[str, dict[str, Any]] = {}
    for card in family:
        for run in card.runs or []:
            meta = _bakeoff_meta(run.handoff)
            if not meta or str(meta.get("id")) != bakeoff_id:
                continue
            label = str(meta.get("label") or "").strip()
            if not label:
                continue
            stage_id = str(meta.get("stage_id") or card.current_stage_id or "")
            stage = stages_by_id.get(stage_id)
            work = _latest_work_run(card, stage_id or None)
            handoff = work.handoff if work and isinstance(work.handoff, dict) else {}
            usage = usage_from_handoff(handoff)
            if not usage.get("provider") and isinstance(handoff.get("llm"), dict):
                usage["provider"] = str(handoff["llm"].get("provider") or "")
            if not usage.get("model") and isinstance(handoff.get("llm"), dict):
                usage["model"] = str(handoff["llm"].get("model") or "")
            config = stage.agent_config if stage else None
            recommendation = handoff.get("recommendation")
            if recommendation not in {"approve", "reject"}:
                recommendation = None
            by_label[label] = {
                "label": label,
                "card_id": card.id,
                "stage_id": stage_id,
                "stage_name": stage.name if stage else label,
                "status": card.status.value if hasattr(card.status, "value") else str(card.status),
                "model": (config.model if config and config.model else "") or str(usage.get("model") or ""),
                "llm_provider": (config.llm_provider if config else "") or str(usage.get("provider") or ""),
                "temperature": float(config.temperature) if config else None,
                "tool_allowlist": list(config.tool_allowlist or [])
                if config
                else list(meta.get("tool_allowlist") or []),
                "system_prompt": (config.system_prompt[:240] if config and config.system_prompt else ""),
                "summary": str(handoff.get("summary") or "").strip(),
                "output": (work.model_output if work else "") or "",
                "recommendation": recommendation,
                "usage": {
                    "prompt_tokens": usage["prompt_tokens"],
                    "completion_tokens": usage["completion_tokens"],
                    "total_tokens": usage["total_tokens"],
                    "rounds": usage["rounds"],
                    "source": usage["source"],
                    "provider": usage.get("provider") or "",
                    "model": usage.get("model") or "",
                },
                "run_id": work.id if work else None,
                "run_status": work.status if work else None,
            }
    return sorted(by_label.values(), key=lambda row: row["label"])


def _compare_status(arms: list[dict[str, Any]]) -> str:
    if not arms:
        return "empty"
    statuses = {str(arm.get("status") or "") for arm in arms}
    if statuses <= {CardStatus.DONE.value}:
        return "ready"
    if statuses & {s.value for s in ACTIVE}:
        return "running"
    if statuses & {CardStatus.WAITING_APPROVAL.value, CardStatus.WAITING_TOOL_APPROVAL.value}:
        return "waiting"
    if statuses & {CardStatus.BLOCKED.value}:
        return "partial"
    if all(status in {s.value for s in SETTLED} | {CardStatus.IDLE.value} for status in statuses):
        return "ready"
    return "partial"


async def bakeoff_compare(session: AsyncSession, card_id: str) -> dict[str, Any] | None:
    result = await session.execute(
        select(Card)
        .where(Card.id == card_id)
        .options(
            selectinload(Card.runs),
            selectinload(Card.board).selectinload(Board.stages).selectinload(Stage.agent_config),
        )
    )
    card = result.scalar_one_or_none()
    if card is None:
        return None
    family = await load_family_cards(session, card)
    bakeoff_id = _find_bakeoff_id(family)
    if not bakeoff_id:
        return {
            "bakeoff_id": None,
            "root_card_id": card.parent_card_id or card.id,
            "board_id": card.board_id,
            "status": "none",
            "prompt": "",
            "arms": [],
            "totals": empty_usage(source="unavailable"),
        }
    stages_by_id = {stage.id: stage for stage in (card.board.stages if card.board else [])}
    arms = _arm_rows_for_id(family, bakeoff_id, stages_by_id)
    totals = empty_usage(source="unavailable")
    prompt = ""
    for arm in arms:
        totals = add_usage(totals, arm.get("usage"))
    for member in family:
        for run in member.runs or []:
            meta = _bakeoff_meta(run.handoff)
            if meta and str(meta.get("id")) == bakeoff_id and meta.get("prompt"):
                prompt = str(meta["prompt"])
                break
        if prompt:
            break
    return {
        "bakeoff_id": bakeoff_id,
        "root_card_id": card.parent_card_id or card.id,
        "board_id": card.board_id,
        "status": _compare_status(arms),
        "prompt": prompt,
        "arms": arms,
        "totals": {
            "prompt_tokens": totals["prompt_tokens"],
            "completion_tokens": totals["completion_tokens"],
            "total_tokens": totals["total_tokens"],
            "rounds": totals["rounds"],
            "source": totals["source"],
        },
    }


async def start_bakeoff(
    session: AsyncSession,
    card_id: str,
    arms: list[dict[str, Any]],
    *,
    prompt: str | None = None,
    require_approval: bool = False,
    auto_start: bool = True,
) -> dict[str, Any]:
    if len(arms) < 2:
        raise BakeoffError("Bakeoff needs at least two arms to compare")
    if len(arms) > 6:
        raise BakeoffError("Bakeoff supports at most 6 arms")

    result = await session.execute(
        select(Card)
        .where(Card.id == card_id)
        .options(
            selectinload(Card.runs),
            selectinload(Card.board).selectinload(Board.stages).selectinload(Stage.agent_config),
            selectinload(Card.board).selectinload(Board.transitions),
        )
    )
    card = result.scalar_one_or_none()
    if card is None:
        raise BakeoffError("Card not found")
    if card.parent_card_id:
        raise BakeoffError("Start bakeoff from the root card, not a parallel track")
    if card.status not in {CardStatus.IDLE, CardStatus.BLOCKED, CardStatus.DONE}:
        raise BakeoffError(
            "Card must be idle, blocked, or done before starting a bakeoff "
            f"(current status: {card.status.value if hasattr(card.status, 'value') else card.status})"
        )
    if not card.current_stage_id or not card.board:
        raise BakeoffError("Card has no stage assigned")

    board = card.board
    source = next((stage for stage in board.stages if stage.id == card.current_stage_id), None)
    if source is None:
        raise BakeoffError("Card stage is not on this board")

    normalized = [_normalize_arm(arm if isinstance(arm, dict) else {}, index) for index, arm in enumerate(arms)]
    labels = [arm["label"] for arm in normalized]
    if len(set(labels)) != len(labels):
        raise BakeoffError("Bakeoff arm labels must be unique")

    shared_body = str(prompt).strip() if isinstance(prompt, str) and prompt.strip() else card.body
    bakeoff_id = str(uuid4())
    order = max((stage.order for stage in board.stages), default=source.order) + 1
    existing_lanes = [stage.lane for stage in board.stages if stage.order == order]
    next_lane = (max(existing_lanes) + 1) if existing_lanes else 0

    arm_stages: list[Stage] = []
    for index, arm in enumerate(normalized):
        stage = Stage(
            board_id=board.id,
            name=f"Bakeoff · {arm['label']}"[:255],
            order=order,
            lane=next_lane + index,
            require_approval=require_approval,
            confirm_writes=False,
            auto_start=False,
        )
        stage.agent_config = AgentConfig(
            system_prompt=arm["system_prompt"],
            model=arm["model"],
            llm_provider=arm["llm_provider"],
            temperature=arm["temperature"],
            tool_allowlist=arm["tool_allowlist"],
            workspace_path=arm["workspace_path"],
            git_url=arm["git_url"],
        )
        session.add(stage)
        arm_stages.append(stage)

    await session.flush()

    # Board chrome: show parallel edges from the source so the machine editor reflects the bakeoff.
    for stage in arm_stages:
        session.add(
            StageTransition(
                board_id=board.id,
                from_stage_id=source.id,
                to_stage_id=stage.id,
                event="approve" if source.require_approval else "auto",
                condition_key="bakeoff_id",
                condition_op="eq",
                condition_value=bakeoff_id,
                order=100 + stage.lane,
            )
        )

    tracks = [
        {
            "stage_id": stage.id,
            "title": f"{card.title} · {normalized[index]['label']}"[:255],
            "body": shared_body,
            "summary": f"Bakeoff arm {normalized[index]['label']}: same prompt, different agent settings.",
        }
        for index, stage in enumerate(arm_stages)
    ]
    handoff: dict[str, Any] = {
        "summary": f"Bakeoff {bakeoff_id[:8]} with {len(arm_stages)} arms.",
        "links": [],
        "attachment_metadata": [],
        "tracks": tracks,
        "bakeoff": {
            "id": bakeoff_id,
            "root_card_id": card.id,
            "prompt": shared_body,
            "arms": [
                {
                    "label": arm["label"],
                    "stage_id": arm_stages[index].id,
                    "tool_allowlist": arm["tool_allowlist"],
                    "model": arm["model"],
                    "llm_provider": arm["llm_provider"],
                }
                for index, arm in enumerate(normalized)
            ],
        },
    }

    # Stamp bakeoff on a seed run before fork so compare can find the id on the root.
    session.add(
        AgentRun(
            card=card,
            stage_id=source.id,
            inputs={"bakeoff_seed": True, "bakeoff_id": bakeoff_id},
            tool_calls=[],
            model_output=f"Started bakeoff with {len(arm_stages)} arms.",
            handoff=dict(handoff),
            status="completed",
            completed_at=utc_now(),
        )
    )
    await session.flush()

    routes = [Route(stage_id=stage.id, found=True) for stage in arm_stages]
    queued = await apply_forward_routes(session, card, list(board.stages) + arm_stages, routes, handoff, auto=True)

    # Re-stamp bakeoff metadata onto each track's seeded handoff (split overwrites track context).
    await session.flush()
    family = await load_family_cards(session, card)
    stage_to_label = {arm_stages[i].id: normalized[i]["label"] for i in range(len(arm_stages))}
    stage_to_tools = {arm_stages[i].id: normalized[i]["tool_allowlist"] for i in range(len(arm_stages))}
    for member in family:
        stage_id = member.current_stage_id or ""
        label = stage_to_label.get(stage_id)
        if not label:
            continue
        for run in member.runs or []:
            if not isinstance(run.handoff, dict):
                continue
            payload = dict(run.handoff)
            payload["bakeoff"] = {
                "id": bakeoff_id,
                "label": label,
                "root_card_id": card.id,
                "stage_id": stage_id,
                "prompt": shared_body,
                "tool_allowlist": stage_to_tools.get(stage_id, []),
            }
            run.handoff = payload

    await session.commit()

    run_ids: list[str] = []
    if auto_start:
        for item_id, stage_id in queued:
            run_ids.append(await enqueue_stage_run(item_id, stage_id))

    compare = await bakeoff_compare(session, card.id)
    assert compare is not None
    compare["queued"] = [{"card_id": item_id, "stage_id": stage_id} for item_id, stage_id in queued]
    compare["run_ids"] = run_ids
    return compare
