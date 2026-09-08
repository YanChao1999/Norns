from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentRun, Card
from ..utc import utc_now
from .state_machine import CardStatus


async def recover_stale_runs(session: AsyncSession, *, older_than_seconds: int) -> int:
    """Mark abandoned in-flight runs failed and block their cards."""
    if older_than_seconds <= 0:
        return 0
    cutoff = utc_now() - timedelta(seconds=older_than_seconds)
    result = await session.execute(select(AgentRun).where(AgentRun.status == "running", AgentRun.created_at < cutoff))
    stale = list(result.scalars().all())
    if not stale:
        return 0
    card_ids = {run.card_id for run in stale}
    cards = list((await session.execute(select(Card).where(Card.id.in_(card_ids)))).scalars().all())
    by_id = {card.id: card for card in cards}
    for run in stale:
        run.status = "failed"
        run.model_output = "Stage run timed out."
        run.completed_at = utc_now()
        card = by_id.get(run.card_id)
        if card and card.status == CardStatus.RUNNING:
            card.status = CardStatus.BLOCKED
    await session.commit()
    return len(stale)
