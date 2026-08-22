from types import SimpleNamespace

from backend.app.orchestrator.progression import next_stage_after
from backend.app.orchestrator.state_machine import CardStatus, auto_advance_card


def test_next_stage_after_returns_following_stage():
    stage_a = SimpleNamespace(id="a", order=1)
    stage_b = SimpleNamespace(id="b", order=2)
    stage_c = SimpleNamespace(id="c", order=3)
    assert next_stage_after([stage_c, stage_a, stage_b], "a").id == "b"
    assert next_stage_after([stage_a, stage_b, stage_c], "c") is None
    assert next_stage_after([stage_a], "missing") is None


def test_auto_advance_moves_to_next_stage_while_running():
    card = SimpleNamespace(status=CardStatus.RUNNING, current_stage_id="stage-a")
    auto_advance_card(card, "stage-b")
    assert card.current_stage_id == "stage-b"
    assert card.status == CardStatus.RUNNING


def test_auto_advance_last_stage_marks_done():
    card = SimpleNamespace(status=CardStatus.RUNNING, current_stage_id="stage-a")
    auto_advance_card(card, None)
    assert card.status == CardStatus.DONE
