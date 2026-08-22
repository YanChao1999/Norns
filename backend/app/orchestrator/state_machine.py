from __future__ import annotations

from enum import Enum


class CardStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    BLOCKED = "blocked"
    DONE = "done"


TRANSITIONS: dict[CardStatus, set[CardStatus]] = {
    CardStatus.IDLE: {CardStatus.RUNNING, CardStatus.BLOCKED},
    CardStatus.RUNNING: {CardStatus.WAITING_APPROVAL, CardStatus.BLOCKED, CardStatus.DONE},
    CardStatus.WAITING_APPROVAL: {CardStatus.RUNNING, CardStatus.BLOCKED, CardStatus.DONE},
    CardStatus.BLOCKED: {CardStatus.RUNNING},
    CardStatus.DONE: set(),
}


def _current_status(card: object) -> CardStatus:
    status = getattr(card, "status")
    return status if isinstance(status, CardStatus) else CardStatus(status)


def transition_card(card: object, target: CardStatus) -> None:
    current = _current_status(card)
    if target not in TRANSITIONS[current]:
        raise ValueError(f"Invalid card transition: {current.value} -> {target.value}")
    setattr(card, "status", target)


def start_card_run(card: object) -> None:
    if _current_status(card) == CardStatus.RUNNING:
        return
    transition_card(card, CardStatus.RUNNING)


def wait_for_approval(card: object) -> None:
    transition_card(card, CardStatus.WAITING_APPROVAL)


def advance_card(card: object, next_stage_id: str | None = None) -> None:
    current = _current_status(card)
    if current not in {CardStatus.WAITING_APPROVAL, CardStatus.BLOCKED}:
        raise ValueError(f"Cannot advance a card from {current.value}")
    if next_stage_id:
        setattr(card, "current_stage_id", next_stage_id)
        setattr(card, "status", CardStatus.RUNNING)
        return
    setattr(card, "status", CardStatus.DONE)


def reject_card_state(card: object) -> None:
    transition_card(card, CardStatus.BLOCKED)
