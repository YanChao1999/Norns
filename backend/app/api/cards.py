from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_session
from ..models import AgentRun, Approval, Board, Card, Stage
from ..orchestrator.enqueue import enqueue_stage_run
from ..orchestrator.gates import approve_card, reject_card
from ..orchestrator.state_machine import CardStatus, start_card_run
from .auth import SessionUser, get_current_user

router = APIRouter(tags=["cards"], dependencies=[Depends(get_current_user)])


class CardCreate(BaseModel):
    title: str = Field(min_length=1)
    body: str = ""
    external_id: str | None = None
    current_stage_id: str | None = None


class CardUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    external_id: str | None = None
    current_stage_id: str | None = None
    status: CardStatus | None = None


class ApprovalRequest(BaseModel):
    approved: bool
    comment: str | None = None


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    card_id: str
    stage_id: str
    agent_run_id: str
    actor: str
    approved: bool
    comment: str | None = None
    created_at: Any


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    card_id: str
    stage_id: str
    inputs: dict
    tool_calls: list
    model_output: str
    handoff: dict
    status: str
    created_at: Any
    completed_at: Any | None = None


class CardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    board_id: str
    title: str
    body: str
    external_id: str | None = None
    current_stage_id: str | None = None
    status: CardStatus
    created_at: Any
    updated_at: Any


@router.get("/boards/{board_id}/cards", response_model=list[CardRead])
async def list_cards(board_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> list[Card]:
    board = await session.get(Board, board_id)
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")
    result = await session.execute(select(Card).where(Card.board_id == board_id).order_by(Card.created_at))
    return list(result.scalars().all())


@router.post("/boards/{board_id}/cards", response_model=CardRead, status_code=status.HTTP_201_CREATED)
async def create_card(board_id: str, payload: CardCreate, session: Annotated[AsyncSession, Depends(get_session)]) -> Card:
    board_result = await session.execute(select(Board).where(Board.id == board_id).options(selectinload(Board.stages)))
    board = board_result.scalar_one_or_none()
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")

    stage_id = payload.current_stage_id or (board.stages[0].id if board.stages else None)
    card = Card(board_id=board_id, title=payload.title, body=payload.body, external_id=payload.external_id, current_stage_id=stage_id)
    session.add(card)
    await session.commit()
    await session.refresh(card)
    return card


@router.get("/cards/{card_id}", response_model=CardRead)
async def get_card(card_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> Card:
    card = await session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@router.put("/cards/{card_id}", response_model=CardRead)
async def update_card(card_id: str, payload: CardUpdate, session: Annotated[AsyncSession, Depends(get_session)]) -> Card:
    card = await session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    updates = payload.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(card, field, value)

    await session.commit()
    await session.refresh(card)
    return card


@router.post("/cards/{card_id}/approve", response_model=ApprovalRead)
async def approve_or_reject_card(
    card_id: str,
    payload: ApprovalRequest,
    current_user: Annotated[SessionUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Approval:
    if payload.approved:
        return await approve_card(session, card_id, current_user.username, payload.comment)
    return await reject_card(session, card_id, current_user.username, payload.comment)


@router.get("/cards/{card_id}/runs", response_model=list[AgentRunRead])
async def list_runs(card_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> list[AgentRun]:
    card = await session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    result = await session.execute(select(AgentRun).where(AgentRun.card_id == card_id).order_by(AgentRun.created_at.desc()))
    return list(result.scalars().all())


@router.post("/cards/{card_id}/run", response_model=dict[str, str], status_code=status.HTTP_202_ACCEPTED)
async def trigger_card_run(card_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
    card_result = await session.execute(select(Card).where(Card.id == card_id).options(selectinload(Card.current_stage)))
    card = card_result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if not card.current_stage_id:
        raise HTTPException(status_code=400, detail="Card has no stage assigned")
    start_card_run(card)
    await session.commit()
    run_id = await enqueue_stage_run(card.id, card.current_stage_id)
    return {"run_id": run_id}
