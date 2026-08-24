from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import Approval, Board, Card, Stage
from .enqueue import EnqueueError, enqueue_stage_run
from .progression import resolve_route, resolve_routes
from .split import apply_forward_routes
from .state_machine import CardStatus, reject_card_state, return_card_to_stage


async def _load_card_for_gate(session: AsyncSession, card_id: str) -> Card:
    result = await session.execute(
        select(Card)
        .where(Card.id == card_id)
        .options(
            selectinload(Card.current_stage).selectinload(Stage.board).selectinload(Board.stages),
            selectinload(Card.current_stage).selectinload(Stage.board).selectinload(Board.transitions),
            selectinload(Card.current_stage)
            .selectinload(Stage.board)
            .selectinload(Board.cards)
            .selectinload(Card.runs),
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


def _latest_stage_run(card: Card):
    return next(
        (
            run
            for run in sorted(card.runs, key=lambda item: (item.created_at or datetime.min, item.id), reverse=True)
            if run.stage_id == card.current_stage_id
        ),
        None,
    )


async def approve_card(session: AsyncSession, card_id: str, actor: str, comment: str | None = None) -> Approval:
    card = await _load_card_for_gate(session, card_id)
    latest_run = _latest_stage_run(card)
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

    board = card.current_stage.board
    handoff = latest_run.handoff if isinstance(latest_run.handoff, dict) else {}
    routes = resolve_routes(board.stages, board.transitions, card.current_stage_id, "approve", handoff)
    queued = await apply_forward_routes(
        session,
        card,
        list(board.stages),
        routes,
        handoff,
        auto=False,
        transitions=list(board.transitions),
        board_cards=list(board.cards),
    )
    await session.commit()
    await session.refresh(approval)

    for card_id, stage_id in queued:
        try:
            await enqueue_stage_run(card_id, stage_id)
        except EnqueueError:
            stuck = await session.get(Card, card_id)
            if stuck:
                stuck.status = CardStatus.BLOCKED
                await session.commit()
            raise
    return approval


async def reject_card(session: AsyncSession, card_id: str, actor: str, comment: str | None = None) -> Approval:
    card = await _load_card_for_gate(session, card_id)
    latest_run = _latest_stage_run(card)
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
    board = card.current_stage.board
    route = resolve_route(
        board.stages,
        board.transitions,
        card.current_stage_id,
        "reject",
        latest_run.handoff if isinstance(latest_run.handoff, dict) else {},
    )
    if route.found and route.stage_id:
        return_card_to_stage(card, route.stage_id)
    elif route.found:
        card.status = CardStatus.DONE
    else:
        reject_card_state(card)
    await session.commit()
    await session.refresh(approval)
    return approval
