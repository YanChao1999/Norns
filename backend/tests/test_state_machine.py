from types import SimpleNamespace

import pytest

from backend.app.orchestrator.state_machine import CardStatus, advance_card, reject_card_state, start_card_run, wait_for_approval


@pytest.mark.parametrize(
    ("initial", "transition"),
    [
        (CardStatus.IDLE, start_card_run),
        (CardStatus.RUNNING, wait_for_approval),
    ],
)
def test_valid_transitions(initial, transition):
    card = SimpleNamespace(status=initial, current_stage_id="stage-a")
    transition(card)
    assert card.status in {CardStatus.RUNNING, CardStatus.WAITING_APPROVAL}


def test_advance_to_next_stage_sets_running():
    card = SimpleNamespace(status=CardStatus.WAITING_APPROVAL, current_stage_id="stage-a")
    advance_card(card, "stage-b")
    assert card.current_stage_id == "stage-b"
    assert card.status == CardStatus.RUNNING


def test_advance_last_stage_marks_done():
    card = SimpleNamespace(status=CardStatus.WAITING_APPROVAL, current_stage_id="stage-a")
    advance_card(card, None)
    assert card.status == CardStatus.DONE


def test_reject_keeps_stage_and_blocks_card():
    card = SimpleNamespace(status=CardStatus.WAITING_APPROVAL, current_stage_id="stage-a")
    reject_card_state(card)
    assert card.current_stage_id == "stage-a"
    assert card.status == CardStatus.BLOCKED


def test_invalid_transition_raises():
    card = SimpleNamespace(status=CardStatus.IDLE, current_stage_id="stage-a")
    with pytest.raises(ValueError):
        wait_for_approval(card)
