from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import Card, Stage
from .enqueue import EnqueueError, enqueue_stage_run
from .state_machine import CardStatus, start_card_run

logger = logging.getLogger("norns")


async def maybe_auto_start_card(session: AsyncSession, card: Card, stage: Stage | None = None) -> str | None:
    """If the card is idle on an auto_start stage, enqueue a run. Returns run_id or None."""
    if card.status != CardStatus.IDLE or not card.current_stage_id:
        return None
    target = stage
    if target is None or target.id != card.current_stage_id:
        target = await session.get(Stage, card.current_stage_id)
    if target is None or not bool(getattr(target, "auto_start", False)):
        return None
    start_card_run(card)
    await session.commit()
    try:
        return await enqueue_stage_run(card.id, card.current_stage_id)
    except EnqueueError as exc:
        card.status = CardStatus.BLOCKED
        await session.commit()
        logger.warning("auto_start enqueue failed card=%s stage=%s: %s", card.id, card.current_stage_id, exc)
        return None


async def pickup_idle_cards_for_stage(session: AsyncSession, stage_id: str) -> list[str]:
    """Enqueue every idle card currently on an auto_start stage. Returns run ids."""
    stage = await session.get(Stage, stage_id)
    if stage is None or not bool(getattr(stage, "auto_start", False)):
        return []
    result = await session.execute(
        select(Card)
        .where(Card.current_stage_id == stage_id, Card.status == CardStatus.IDLE)
        .options(selectinload(Card.current_stage))
    )
    run_ids: list[str] = []
    for card in result.scalars().all():
        run_id = await maybe_auto_start_card(session, card, stage)
        if run_id:
            run_ids.append(run_id)
    return run_ids
