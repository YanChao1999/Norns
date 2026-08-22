from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import AgentRun, Approval, Board, Card, Stage
from .enqueue import enqueue_stage_run
from .progression import next_stage_after
from .state_machine import CardStatus, advance_card, reject_card_state


async def _load_card_for_gate(session: AsyncSession, card_id: str) -> Card:
    result = await session.execute(
        select(Card)
        .where(Card.id == card_id)
        .options(
            selectinload(Card.current_stage).selectinload(Stage.board).selectinload(Board.stages),
            selectinload(Card.runs),
        )
    )
    card = result.scalar_one_or_none()
    if not card:
        raise ValueError("Card not found")
    if card.status != CardStatus.WAITING_APPROVAL:
        raise ValueError("Card is not waiting for approval")
    if not card.current_stage:
        raise ValueError("Card has no current stage")
    return card


async def approve_card(session: AsyncSession, card_id: str, actor: str, comment: str | None = None) -> Approval:
    card = await _load_card_for_gate(session, card_id)
    latest_run = next(
        (
            run
            for run in sorted(card.runs, key=lambda item: (item.created_at or datetime.min, item.id), reverse=True)
            if run.stage_id == card.current_stage_id
        ),
        None,
    )
    if not latest_run:
        raise ValueError("No agent run available for approval")

    approval = Approval(
        card_id=card.id,
        stage_id=card.current_stage_id,
        agent_run_id=latest_run.id,
        actor=actor,
        approved=True,
        comment=comment,
    )
    session.add(approval)

    next_stage = next_stage_after(card.current_stage.board.stages, card.current_stage_id)
    advance_card(card, next_stage.id if next_stage else None)
    await session.commit()
    await session.refresh(approval)

    if next_stage:
        await enqueue_stage_run(card.id, next_stage.id)
    return approval


async def reject_card(session: AsyncSession, card_id: str, actor: str, comment: str | None = None) -> Approval:
    card = await _load_card_for_gate(session, card_id)
    latest_run = next(
        (
            run
            for run in sorted(card.runs, key=lambda item: (item.created_at or datetime.min, item.id), reverse=True)
            if run.stage_id == card.current_stage_id
        ),
        None,
    )
    if not latest_run:
        raise ValueError("No agent run available for approval")

    approval = Approval(
        card_id=card.id,
        stage_id=card.current_stage_id,
        agent_run_id=latest_run.id,
        actor=actor,
        approved=False,
        comment=comment,
    )
    session.add(approval)
    reject_card_state(card)
    await session.commit()
    await session.refresh(approval)
    return approval
