from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentRun, Card, Stage, StageTransition
from .progression import Route, incoming_join_sources, is_join_stage, target_stage_ids
from .state_machine import CardStatus, auto_advance_card, advance_card


def apply_forward_routes(
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
    targets = target_stage_ids(routes)
    if not targets:
        if auto:
            auto_advance_card(card, None)
        else:
            advance_card(card, None)
        return []

    names = {stage.id: stage.name for stage in stages}
    first, *rest = targets
    spawned = [_fork_card(session, card, stage_id, names.get(stage_id, "track"), handoff) for stage_id in rest]
    placements = [(card, first), *zip(spawned, rest, strict=True)]
    family = _family(card, list(board_cards or []) + spawned)
    edges = list(transitions or [])

    queued: list[tuple[str, str]] = []
    for item, stage_id in placements:
        item.current_stage_id = stage_id
        if _wait_for_join(item, stage_id, family, edges, stages):
            item.status = CardStatus.WAITING_JOIN
            continue
        survivor = _finalize_join(session, item, stage_id, family, handoff, edges, stages)
        survivor.status = CardStatus.RUNNING
        queued.append((survivor.id, stage_id))
    return queued


def _fork_card(
    session: AsyncSession,
    parent: Card,
    stage_id: str,
    stage_name: str,
    handoff: dict[str, Any],
) -> Card:
    suffix = f" · {stage_name}"
    title = parent.title if parent.title.endswith(suffix) else f"{parent.title}{suffix}"
    child = Card(
        id=str(uuid4()),
        board_id=parent.board_id,
        title=title[:255],
        body=parent.body,
        external_id=parent.external_id,
        current_stage_id=stage_id,
        parent_card_id=parent.id,
        status=CardStatus.RUNNING,
    )
    session.add(child)
    session.add(
        AgentRun(
            card=child,
            stage_id=parent.current_stage_id or stage_id,
            inputs={"forked_from": parent.id},
            tool_calls=[],
            model_output=f"Parallel track for {stage_name}.",
            handoff=handoff if isinstance(handoff, dict) else {},
            status="completed",
            completed_at=datetime.utcnow(),
        )
    )
    return child


def _family(card: Card, extras: list[Card]) -> list[Card]:
    root = card.parent_card_id or card.id
    found: dict[str, Card] = {card.id: card}
    for item in extras:
        if item.id == root or item.parent_card_id == root:
            found[item.id] = item
    return list(found.values())


def _wait_for_join(
    card: Card,
    target_id: str,
    family: list[Card],
    transitions: list[StageTransition],
    stages: list[Stage],
) -> bool:
    if not is_join_stage(transitions, target_id, stages):
        return False
    if len({item.id for item in family}) < 2:
        return False
    sources = set(incoming_join_sources(transitions, target_id, stages))
    return any(item.id != card.id and item.current_stage_id in sources for item in family)


def _finalize_join(
    session: AsyncSession,
    arriving: Card,
    stage_id: str,
    family: list[Card],
    handoff: dict[str, Any],
    transitions: list[StageTransition],
    stages: list[Stage],
) -> Card:
    if not is_join_stage(transitions, stage_id, stages) or len({item.id for item in family}) < 2:
        return arriving

    at_join = [item for item in family if item.current_stage_id == stage_id]
    root = arriving.parent_card_id or arriving.id
    survivor = next((item for item in at_join if item.id == root), arriving)
    tracks = []
    links: list[str] = []
    summaries: list[str] = []
    for item in at_join:
        payload = _latest_handoff(item)
        if item.id == arriving.id and not payload:
            payload = handoff if isinstance(handoff, dict) else {}
        payload = payload if isinstance(payload, dict) else {}
        tracks.append({"card_id": item.id, "title": item.title, "handoff": payload})
        summary = payload.get("summary")
        if isinstance(summary, str) and summary.strip():
            summaries.append(f"{item.title}: {summary.strip()}")
        extra_links = payload.get("links")
        if isinstance(extra_links, list):
            links.extend(str(link) for link in extra_links)

    session.add(
        AgentRun(
            card=survivor,
            stage_id=stage_id,
            inputs={"joined_cards": [item.id for item in at_join]},
            tool_calls=[],
            model_output="Joined parallel tracks.",
            handoff={
                "summary": "\n\n".join(summaries) or "Parallel tracks joined.",
                "tracks": tracks,
                "links": links,
            },
            status="completed",
            completed_at=datetime.utcnow(),
        )
    )
    for item in at_join:
        if item.id != survivor.id:
            item.status = CardStatus.DONE
    return survivor


def _latest_handoff(card: Card) -> dict[str, Any]:
    completed = [run for run in getattr(card, "runs", []) if getattr(run, "status", None) == "completed"]
    if not completed:
        return {}
    latest = sorted(completed, key=lambda run: (run.created_at or datetime.min, run.id))[-1]
    payload = latest.handoff
    return payload if isinstance(payload, dict) else {}
