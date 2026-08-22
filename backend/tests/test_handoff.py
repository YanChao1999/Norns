from types import SimpleNamespace

import pytest

from backend.app.agents.runner import _latest_handoff
from backend.app.tools.polarion import assert_writable_field


def test_latest_handoff_ignores_in_progress_run():
    card = SimpleNamespace(
        runs=[
            SimpleNamespace(status="completed", created_at=1, handoff={"summary": "stage-1"}),
            SimpleNamespace(status="running", created_at=2, handoff={}),
        ]
    )
    assert _latest_handoff(card) == {"summary": "stage-1"}


def test_latest_handoff_empty_when_no_completed_runs():
    card = SimpleNamespace(runs=[SimpleNamespace(status="running", created_at=1, handoff={})])
    assert _latest_handoff(card) is None


def test_polarion_rejects_arbitrary_fields():
    assert assert_writable_field("status") == "status"
    with pytest.raises(ValueError):
        assert_writable_field("__class__")
