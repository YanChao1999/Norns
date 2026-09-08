from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import AgentRun, Card, Stage, StageTransition
from ..utc import utc_now
from .progression import Route, target_stage_ids
from .state_machine import CardStatus, advance_card, auto_advance_card


async def apply_forward_routes(
    session: AsyncSession,
    card: Card,
    stages: list[Stage],
    routes: list[Route],
    handoff: dict[str, Any],
    *,
    auto: bool,
    transitions: list[StageTransition] | None = None,
    board_cards: list[Card] | None = None,
) -> list[tuple[str, str]]:
    """Move the card (and fork siblings) along resolved routes. Returns (card_id, stage_id) to enqueue."""
    del transitions, board_cards  # soft join: no wait/merge; family lock unused
    targets = target_stage_ids(routes)
    if not targets:
        if auto:
            auto_advance_card(card, None)
        else:
            advance_card(card, None)
        return []

    names = {stage.id: stage.name for stage in stages}
    plans = _track_plans(targets, names, card, handoff)
    first_stage, *rest_stages = targets
    first_plan = plans[0]
    _apply_track_plan(card, first_plan, names.get(first_stage, "track"))
    seeded = _track_seed_handoff(handoff, first_plan)
    if len(targets) > 1:
        # Root keeps only its track context for the next agent.
        session.add(
            AgentRun(
                card=card,
                stage_id=card.current_stage_id or first_stage,
                inputs={"split_plan": True, "track": first_plan},
                tool_calls=[],
                model_output=f"Parallel track for {names.get(first_stage, 'track')}.",
                handoff=seeded,
                status="completed",
                completed_at=utc_now(),
            )
        )
    spawned = [
        _fork_card(session, card, stage_id, names.get(stage_id, "track"), handoff, plans[index + 1])
        for index, stage_id in enumerate(rest_stages)
    ]
    await session.flush()

    placements = [(card, first_stage), *zip(spawned, rest_stages, strict=True)]
    queued: list[tuple[str, str]] = []
    for item, stage_id in placements:
        item.current_stage_id = stage_id
        item.status = CardStatus.RUNNING
        queued.append((item.id, stage_id))
    return queued


def _track_plans(
    targets: list[str],
    names: dict[str, str],
    card: Card,
    handoff: dict[str, Any],
) -> list[dict[str, Any]]:
    raw = handoff.get("tracks") if isinstance(handoff, dict) else None
    parsed = _normalize_tracks(raw) if isinstance(raw, list) else []
    use_plans = len(parsed) == len(targets) and len(targets) > 0
    by_stage = {
        str(item["stage_id"]): item
        for item in parsed
        if use_plans and isinstance(item.get("stage_id"), str) and str(item.get("stage_id") or "").strip()
    }
    plans: list[dict[str, Any]] = []
    for index, stage_id in enumerate(targets):
        matched: dict[str, Any] | None = None
        if use_plans:
            matched = by_stage.get(stage_id)
            if matched is None:
                matched = parsed[index]
        stage_name = names.get(stage_id, "track")
        if matched is None:
            if index == 0:
                title = card.title
            else:
                suffix = f" · {stage_name}"
                title = card.title if card.title.endswith(suffix) else f"{card.title}{suffix}"
            plans.append(
                {
                    "stage_id": stage_id,
                    "title": title[:255],
                    "body": card.body,
                    "summary": "",
                }
            )
            continue
        title = str(matched.get("title") or "").strip() or (
            card.title if index == 0 else f"{card.title} · {stage_name}"
        )
        body = matched.get("body")
        if not isinstance(body, str) or not body.strip():
            body = card.body
        summary = matched.get("summary")
        plans.append(
            {
                "stage_id": stage_id,
                "title": title[:255],
                "body": body,
                "summary": str(summary).strip() if isinstance(summary, str) else "",
            }
        )
    return plans


def _normalize_tracks(raw: list[Any]) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        tracks.append(
            {
                "stage_id": str(item.get("stage_id") or "").strip() or None,
                "title": str(item.get("title") or "").strip(),
                "body": item.get("body") if isinstance(item.get("body"), str) else "",
                "summary": str(item.get("summary") or "").strip(),
            }
        )
    return tracks


def _apply_track_plan(card: Card, plan: dict[str, Any], stage_name: str) -> None:
    title = str(plan.get("title") or "").strip()
    if title:
        card.title = title[:255]
    elif stage_name:
        suffix = f" · {stage_name}"
        if not card.title.endswith(suffix):
            card.title = f"{card.title}{suffix}"[:255]
    body = plan.get("body")
    if isinstance(body, str) and body.strip():
        card.body = body


def _track_seed_handoff(parent_handoff: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    summary = str(plan.get("summary") or "").strip()
    parent_summary = ""
    if isinstance(parent_handoff, dict):
        raw = parent_handoff.get("summary")
        if isinstance(raw, str):
            parent_summary = raw.strip()
    payload: dict[str, Any] = {
        "summary": summary or parent_summary or f"Parallel track for {plan.get('stage_id') or 'stage'}.",
        "links": list(parent_handoff.get("links") or []) if isinstance(parent_handoff, dict) else [],
        "attachment_metadata": [],
        "track": {
            "stage_id": plan.get("stage_id"),
            "title": plan.get("title"),
            "summary": summary,
        },
    }
    if isinstance(parent_handoff, dict):
        for key in ("recommendation", "recommendation_reason", "llm", "plantuml"):
            if key in parent_handoff:
                payload[key] = parent_handoff[key]
    return payload


def _fork_card(
    session: AsyncSession,
    parent: Card,
    stage_id: str,
    stage_name: str,
    handoff: dict[str, Any],
    plan: dict[str, Any],
) -> Card:
    title = str(plan.get("title") or "").strip()
    if not title:
        suffix = f" · {stage_name}"
        title = parent.title if parent.title.endswith(suffix) else f"{parent.title}{suffix}"
    body = plan.get("body")
    if not isinstance(body, str) or not body.strip():
        body = parent.body
    child = Card(
        id=str(uuid4()),
        board_id=parent.board_id,
        title=title[:255],
        body=body,
        external_id=parent.external_id,
        current_stage_id=stage_id,
        parent_card_id=_root_id(parent),
        status=CardStatus.RUNNING,
    )
    session.add(child)
    session.add(
        AgentRun(
            card=child,
            stage_id=parent.current_stage_id or stage_id,
            inputs={"forked_from": parent.id, "track": plan},
            tool_calls=[],
            model_output=f"Parallel track for {stage_name}.",
            handoff=_track_seed_handoff(handoff, plan),
            status="completed",
            completed_at=utc_now(),
        )
    )
    return child


def _root_id(card: Card) -> str:
    return card.parent_card_id or card.id


async def load_family_cards(session: AsyncSession, card: Card) -> list[Card]:
    """Load the root card and its parallel tracks, with runs, not the whole board."""
    root = _root_id(card)
    result = await session.execute(
        select(Card)
        .where(Card.board_id == card.board_id, or_(Card.id == root, Card.parent_card_id == root))
        .options(selectinload(Card.runs))
    )
    found = list(result.scalars().unique().all())
    if not any(item.id == card.id for item in found):
        found.append(card)
    return found
