"""Aggregate token usage for a card (one task) or a whole board across stage agents."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import AgentRun, Board, Card
from .token_usage import add_usage, empty_usage, usage_from_handoff


def _is_finalized(run: AgentRun) -> bool:
    """Match frontend ``isFinalizedRun`` — exclude active / waiting_tool runs."""
    status = str(run.status or "")
    if status in {"running", "pending", "waiting_tool"}:
        return False
    return status in {"completed", "failed"} or run.completed_at is not None


async def card_usage_matrix(session: AsyncSession, card_id: str) -> dict[str, Any] | None:
    result = await session.execute(
        select(Card).where(Card.id == card_id).options(selectinload(Card.board).selectinload(Board.stages))
    )
    card = result.scalar_one_or_none()
    if card is None:
        return None
    board = card.board
    stages = sorted(board.stages, key=lambda item: (item.order, item.lane or 0, item.name)) if board else []
    runs_result = await session.execute(
        select(AgentRun).where(AgentRun.card_id == card_id).order_by(AgentRun.created_at)
    )
    runs = list(runs_result.scalars().all())

    by_stage: list[dict[str, Any]] = []
    totals = empty_usage(source="unavailable")
    for stage in stages:
        stage_runs = [run for run in runs if run.stage_id == stage.id and _is_finalized(run)]
        stage_total = empty_usage(source="unavailable")
        run_rows: list[dict[str, Any]] = []
        provider = ""
        model = ""
        for run in stage_runs:
            usage = usage_from_handoff(run.handoff)
            stage_total = add_usage(stage_total, usage)
            if usage.get("provider"):
                provider = str(usage["provider"])
            if usage.get("model"):
                model = str(usage["model"])
            run_rows.append(
                {
                    "run_id": run.id,
                    "status": run.status,
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                    "prompt_tokens": usage["prompt_tokens"],
                    "completion_tokens": usage["completion_tokens"],
                    "total_tokens": usage["total_tokens"],
                    "rounds": usage["rounds"],
                    "source": usage["source"],
                    "provider": usage.get("provider") or "",
                    "model": usage.get("model") or "",
                }
            )
        totals = add_usage(totals, stage_total)
        by_stage.append(
            {
                "stage_id": stage.id,
                "stage_name": stage.name,
                "order": stage.order,
                "prompt_tokens": stage_total["prompt_tokens"],
                "completion_tokens": stage_total["completion_tokens"],
                "total_tokens": stage_total["total_tokens"],
                "rounds": stage_total["rounds"],
                "source": stage_total["source"],
                "provider": provider,
                "model": model,
                "run_count": len(run_rows),
                "runs": run_rows,
            }
        )

    return {
        "card_id": card.id,
        "board_id": card.board_id,
        "totals": {
            "prompt_tokens": totals["prompt_tokens"],
            "completion_tokens": totals["completion_tokens"],
            "total_tokens": totals["total_tokens"],
            "rounds": totals["rounds"],
            "source": totals["source"],
        },
        "by_stage": by_stage,
    }


async def board_usage_matrix(session: AsyncSession, board_id: str) -> dict[str, Any] | None:
    """Aggregate token usage across every card on a board (summary dashboard)."""
    result = await session.execute(
        select(Board).where(Board.id == board_id).options(selectinload(Board.stages), selectinload(Board.cards))
    )
    board = result.scalar_one_or_none()
    if board is None:
        return None

    stages = sorted(board.stages, key=lambda item: (item.order, item.lane or 0, item.name))
    cards = list(board.cards)
    card_ids = [card.id for card in cards]
    runs: list[AgentRun] = []
    if card_ids:
        runs_result = await session.execute(
            select(AgentRun).where(AgentRun.card_id.in_(card_ids)).order_by(AgentRun.created_at)
        )
        runs = list(runs_result.scalars().all())

    finalized = [run for run in runs if _is_finalized(run)]
    totals = empty_usage(source="unavailable")
    by_stage: list[dict[str, Any]] = []
    for stage in stages:
        stage_runs = [run for run in finalized if run.stage_id == stage.id]
        stage_total = empty_usage(source="unavailable")
        provider = ""
        model = ""
        for run in stage_runs:
            usage = usage_from_handoff(run.handoff)
            stage_total = add_usage(stage_total, usage)
            if usage.get("provider"):
                provider = str(usage["provider"])
            if usage.get("model"):
                model = str(usage["model"])
        totals = add_usage(totals, stage_total)
        by_stage.append(
            {
                "stage_id": stage.id,
                "stage_name": stage.name,
                "order": stage.order,
                "prompt_tokens": stage_total["prompt_tokens"],
                "completion_tokens": stage_total["completion_tokens"],
                "total_tokens": stage_total["total_tokens"],
                "rounds": stage_total["rounds"],
                "source": stage_total["source"],
                "provider": provider,
                "model": model,
                "run_count": len(stage_runs),
            }
        )

    by_card: list[dict[str, Any]] = []
    for card in sorted(cards, key=lambda item: item.created_at or item.id):
        card_runs = [run for run in finalized if run.card_id == card.id]
        if not card_runs:
            continue
        card_total = empty_usage(source="unavailable")
        for run in card_runs:
            card_total = add_usage(card_total, usage_from_handoff(run.handoff))
        if card_total["total_tokens"] == 0 and card_total["rounds"] == 0:
            continue
        by_card.append(
            {
                "card_id": card.id,
                "title": card.title,
                "prompt_tokens": card_total["prompt_tokens"],
                "completion_tokens": card_total["completion_tokens"],
                "total_tokens": card_total["total_tokens"],
                "rounds": card_total["rounds"],
                "source": card_total["source"],
                "run_count": len(card_runs),
            }
        )
    by_card.sort(key=lambda row: (-int(row["total_tokens"]), str(row["title"])))

    return {
        "board_id": board.id,
        "totals": {
            "prompt_tokens": totals["prompt_tokens"],
            "completion_tokens": totals["completion_tokens"],
            "total_tokens": totals["total_tokens"],
            "rounds": totals["rounds"],
            "source": totals["source"],
        },
        "card_count": len(by_card),
        "run_count": len(finalized),
        "by_stage": by_stage,
        "by_card": by_card,
    }
