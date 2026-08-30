from __future__ import annotations

from typing import Any

from .models import AgentRun, Card

_FINAL_RUN_STATUSES = {"completed", "failed"}


def latest_recommendation(card: Card) -> tuple[str | None, str | None]:
    """Return the current stage's latest agent recommend line, if any."""
    runs = [run for run in getattr(card, "runs", None) or [] if _is_finalized(run)]
    if not runs:
        return None, None
    stage_id = card.current_stage_id
    stage_runs = [run for run in runs if stage_id and run.stage_id == stage_id]
    latest = max(stage_runs or runs, key=lambda run: run.created_at)
    return _recommendation_from_handoff(latest.handoff)


def _is_finalized(run: AgentRun) -> bool:
    return run.status in _FINAL_RUN_STATUSES or bool(run.completed_at)


def _recommendation_from_handoff(handoff: Any) -> tuple[str | None, str | None]:
    if not isinstance(handoff, dict):
        return None, None
    raw = handoff.get("recommendation")
    recommendation = raw.strip().lower() if isinstance(raw, str) else ""
    if recommendation not in {"approve", "reject"}:
        return None, None
    reason_raw = handoff.get("recommendation_reason")
    reason = reason_raw.strip() if isinstance(reason_raw, str) and reason_raw.strip() else None
    return recommendation, reason
