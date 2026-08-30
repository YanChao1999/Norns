from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from backend.app.card_preview import latest_recommendation


def test_latest_recommendation_uses_current_stage_run():
    older = SimpleNamespace(
        stage_id="urd",
        status="completed",
        completed_at=datetime(2026, 1, 1),
        created_at=datetime(2026, 1, 1),
        handoff={"recommendation": "approve", "recommendation_reason": "old"},
    )
    current = SimpleNamespace(
        stage_id="urd",
        status="completed",
        completed_at=datetime(2026, 1, 2),
        created_at=datetime(2026, 1, 2),
        handoff={"recommendation": "reject", "recommendation_reason": "Polarion client is broken."},
    )
    prior_stage = SimpleNamespace(
        stage_id="intake",
        status="completed",
        completed_at=datetime(2026, 1, 3),
        created_at=datetime(2026, 1, 3),
        handoff={"recommendation": "approve", "recommendation_reason": "prior stage"},
    )
    card = SimpleNamespace(current_stage_id="urd", runs=[older, current, prior_stage])
    assert latest_recommendation(card) == ("reject", "Polarion client is broken.")


def test_latest_recommendation_ignores_in_progress_runs():
    card = SimpleNamespace(
        current_stage_id="urd",
        runs=[
            SimpleNamespace(
                stage_id="urd",
                status="running",
                completed_at=None,
                created_at=datetime(2026, 1, 4),
                handoff={"recommendation": "reject", "recommendation_reason": "not done"},
            )
        ],
    )
    assert latest_recommendation(card) == (None, None)
