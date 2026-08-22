from __future__ import annotations

from collections.abc import Sequence

from ..models import Stage


def next_stage_after(stages: Sequence[Stage], current_stage_id: str) -> Stage | None:
    ordered = sorted(stages, key=lambda stage: stage.order)
    current_index = next((index for index, stage in enumerate(ordered) if stage.id == current_stage_id), None)
    if current_index is None or current_index + 1 >= len(ordered):
        return None
    return ordered[current_index + 1]
