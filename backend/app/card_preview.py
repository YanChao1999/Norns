from __future__ import annotations

import re
from typing import Any

from .models import AgentRun, Card

_FINAL_RUN_STATUSES = {"completed", "failed"}


def _card_runs(card: Card) -> list[AgentRun]:
    """Avoid lazy IO during response validation (sync pydantic hooks)."""
    from sqlalchemy import inspect as sa_inspect

    try:
        state = sa_inspect(card)
    except Exception:  # noqa: BLE001
        return list(getattr(card, "runs", None) or [])
    if "runs" in getattr(state, "unloaded", set()):
        return []
    try:
        return list(card.runs or [])
    except Exception:  # noqa: BLE001
        return []


def _latest_finalized_run(card: Card) -> AgentRun | None:
    runs = [run for run in _card_runs(card) if _is_finalized(run)]
    if not runs:
        return None
    stage_id = card.current_stage_id
    stage_runs = [run for run in runs if stage_id and run.stage_id == stage_id]
    return max(stage_runs or runs, key=lambda run: run.created_at)


def latest_recommendation(card: Card) -> tuple[str | None, str | None]:
    """Return the current stage's latest agent recommend line, if any."""
    latest = _latest_finalized_run(card)
    if latest is None:
        return None, None
    return _recommendation_from_handoff(latest.handoff)


def latest_practice(card: Card) -> bool:
    """True when the current stage's latest finalized handoff is a practice/placeholder run."""
    latest = _latest_finalized_run(card)
    if latest is None or not isinstance(latest.handoff, dict):
        return False
    if latest.handoff.get("placeholder") is True:
        return True
    summary = str(latest.handoff.get("summary") or latest.model_output or "")
    return bool(re.search(r"practice run|api key not configured", summary, re.I))


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
