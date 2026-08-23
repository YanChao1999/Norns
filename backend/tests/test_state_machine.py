from types import SimpleNamespace

import pytest

from backend.app.orchestrator.state_machine import (
    CardStatus,
    advance_card,
    auto_advance_card,
    reject_card_state,
    return_card_to_stage,
    start_card_run,
    wait_for_approval,
)


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


def test_return_from_gate_sets_idle_on_previous_stage():
    card = SimpleNamespace(status=CardStatus.WAITING_APPROVAL, current_stage_id="stage-b")
    return_card_to_stage(card, "stage-a")
    assert card.current_stage_id == "stage-a"
    assert card.status == CardStatus.IDLE


def test_invalid_transition_raises():
    card = SimpleNamespace(status=CardStatus.IDLE, current_stage_id="stage-a")
    with pytest.raises(ValueError):
        wait_for_approval(card)


def test_auto_advance_rejects_non_running_cards():
    card = SimpleNamespace(status=CardStatus.WAITING_APPROVAL, current_stage_id="stage-a")
    with pytest.raises(ValueError):
        auto_advance_card(card, "stage-b")
