from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..models import Stage, StageTransition


@dataclass(frozen=True)
class Route:
    stage_id: str | None
    found: bool


def next_stage_after(stages: Sequence[Stage], current_stage_id: str) -> Stage | None:
    ordered = sorted(stages, key=lambda stage: (stage.order, getattr(stage, "lane", 0)))
    current = next((stage for stage in ordered if stage.id == current_stage_id), None)
    if current is None:
        return None
    nxt = [stage for stage in ordered if stage.order > current.order]
    return nxt[0] if nxt else None


def resolve_routes(
    stages: Sequence[Stage],
    transitions: Sequence[StageTransition],
    from_stage_id: str,
    event: str,
    handoff: dict[str, Any] | None = None,
) -> list[Route]:
    matching = [edge for edge in transitions if edge.from_stage_id == from_stage_id and edge.event == event]
    if event == "auto" and not matching:
        matching = [edge for edge in transitions if edge.from_stage_id == from_stage_id and edge.event == "approve"]
    matching = sorted(matching, key=lambda edge: edge.order)
    payload = handoff or {}
    conditioned = [edge for edge in matching if edge.condition_key.strip()]
    defaults = [edge for edge in matching if not edge.condition_key.strip()]
    matched_ifs = [edge for edge in conditioned if _condition_matches(payload, edge)]
    if event == "reject":
        if matched_ifs:
            return [Route(matched_ifs[0].to_stage_id, True)]
        if defaults:
            return [Route(defaults[0].to_stage_id, True)]
        return [Route(None, False)]
    if matched_ifs:
        return [Route(edge.to_stage_id, True) for edge in matched_ifs]
    forward = [edge for edge in defaults if _is_forward(stages, from_stage_id, edge.to_stage_id)]
    chosen = forward or defaults
    if chosen:
        return [Route(edge.to_stage_id, True) for edge in chosen]
    nxt = next_stage_after(stages, from_stage_id)
    return [Route(nxt.id if nxt else None, False)]


def resolve_route(
    stages: Sequence[Stage],
    transitions: Sequence[StageTransition],
    from_stage_id: str,
    event: str,
    handoff: dict[str, Any] | None = None,
) -> Route:
    return resolve_routes(stages, transitions, from_stage_id, event, handoff)[0]


def target_stage_ids(routes: Sequence[Route]) -> list[str]:
    seen: list[str] = []
    for route in routes:
        if route.stage_id and route.stage_id not in seen:
            seen.append(route.stage_id)
    return seen


def incoming_join_sources(
    transitions: Sequence[StageTransition],
    stage_id: str,
    stages: Sequence[Stage] | None = None,
) -> list[str]:
    sources: list[str] = []
    for edge in transitions:
        if edge.to_stage_id != stage_id or edge.condition_key.strip() or edge.event not in {"approve", "auto"}:
            continue
        if stages is not None and not _is_forward(stages, edge.from_stage_id, stage_id):
            continue
        if edge.from_stage_id not in sources:
            sources.append(edge.from_stage_id)
    return sources


def is_join_stage(
    transitions: Sequence[StageTransition],
    stage_id: str,
    stages: Sequence[Stage] | None = None,
) -> bool:
    """True when multiple default forward lines enter a stage (soft join — no wait/merge)."""
    return len(incoming_join_sources(transitions, stage_id, stages)) >= 2


def outgoing_parallel_targets(
    stages: Sequence[Stage],
    transitions: Sequence[StageTransition],
    from_stage_id: str,
    *,
    event: str = "approve",
) -> list[Stage]:
    """Default forward targets that would fan out from this stage (ignore handoff Ifs)."""
    matching = [edge for edge in transitions if edge.from_stage_id == from_stage_id and edge.event == event]
    if event == "auto" and not matching:
        matching = [edge for edge in transitions if edge.from_stage_id == from_stage_id and edge.event == "approve"]
    defaults = sorted(
        [edge for edge in matching if not edge.condition_key.strip()],
        key=lambda edge: edge.order,
    )
    forward = [edge for edge in defaults if _is_forward(stages, from_stage_id, edge.to_stage_id)]
    chosen = forward or defaults
    by_id = {stage.id: stage for stage in stages}
    targets: list[Stage] = []
    seen: set[str] = set()
    for edge in chosen:
        stage = by_id.get(edge.to_stage_id)
        if stage is None or stage.id in seen:
            continue
        seen.add(stage.id)
        targets.append(stage)
    return targets


def _stage_order(stages: Sequence[Stage], stage_id: str | None) -> int | None:
    if not stage_id:
        return None
    stage = next((item for item in stages if item.id == stage_id), None)
    return None if stage is None else stage.order


def _is_forward(stages: Sequence[Stage], from_stage_id: str, to_stage_id: str | None) -> bool:
    if to_stage_id is None:
        return True
    current = _stage_order(stages, from_stage_id)
    target = _stage_order(stages, to_stage_id)
    if current is None or target is None:
        return True
    return target > current


def _condition_text(current: Any) -> str:
    if current is None:
        return ""
    if isinstance(current, bool):
        return "true" if current else "false"
    return str(current)


def _condition_matches(handoff: dict[str, Any], edge: StageTransition) -> bool:
    current: Any = handoff
    for part in edge.condition_key.split("."):
        if not isinstance(current, dict) or part not in current:
            current = None
            break
        current = current[part]
    op = edge.condition_op or "eq"
    if op == "exists":
        return current is not None
    text = _condition_text(current)
    value = edge.condition_value
    if op == "contains":
        if not value:
            return False
        return value.lower() in text.lower()
    return text == value
