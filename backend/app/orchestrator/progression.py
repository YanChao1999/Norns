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
    ordered = sorted(stages, key=lambda stage: stage.order)
    current_index = next((index for index, stage in enumerate(ordered) if stage.id == current_stage_id), None)
    if current_index is None or current_index + 1 >= len(ordered):
        return None
    return ordered[current_index + 1]


def resolve_route(
    stages: Sequence[Stage],
    transitions: Sequence[StageTransition],
    from_stage_id: str,
    event: str,
    handoff: dict[str, Any] | None = None,
) -> Route:
    matching = [edge for edge in transitions if edge.from_stage_id == from_stage_id and edge.event == event]
    if event == "auto" and not matching:
        matching = [edge for edge in transitions if edge.from_stage_id == from_stage_id and edge.event == "approve"]
    matching = sorted(matching, key=lambda edge: edge.order)
    payload = handoff or {}
    conditioned = [edge for edge in matching if edge.condition_key.strip()]
    defaults = [edge for edge in matching if not edge.condition_key.strip()]
    for edge in conditioned:
        if _condition_matches(payload, edge):
            return Route(edge.to_stage_id, True)
    if defaults:
        return Route(defaults[0].to_stage_id, True)
    if event == "reject":
        return Route(None, False)
    nxt = next_stage_after(stages, from_stage_id)
    return Route(nxt.id if nxt else None, False)


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
    text = "" if current is None else str(current)
    value = edge.condition_value
    if op == "contains":
        return value.lower() in text.lower()
    return text == value
