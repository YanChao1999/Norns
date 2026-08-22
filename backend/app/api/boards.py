from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_session
from ..models import AgentConfig, Board, Card, Stage
from .auth import SessionUser, get_current_user

router = APIRouter(tags=["boards"], dependencies=[Depends(get_current_user)])


class AgentConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    system_prompt: str
    model: str
    temperature: float
    tool_allowlist: list[str]


class StageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    board_id: str
    name: str
    order: int
    require_approval: bool
    agent_config: AgentConfigRead | None = None


class CardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    board_id: str
    title: str
    body: str
    external_id: str | None = None
    current_stage_id: str | None = None
    status: str


class BoardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    created_at: Any
    updated_at: Any
    stages: list[StageRead] = []


class BoardDetail(BoardRead):
    cards: list[CardRead] = []


class BoardCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class BoardUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class StageCreate(BaseModel):
    name: str = Field(min_length=1)
    order: int | None = None
    require_approval: bool = True
    system_prompt: str = "You are the stage agent. Produce a concise handoff for the next stage."
    model: str = "gpt-4o"
    temperature: float = 0.7
    tool_allowlist: list[str] = []


class StageUpdate(BaseModel):
    name: str | None = None
    order: int | None = None
    require_approval: bool | None = None
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = None
    tool_allowlist: list[str] | None = None


@router.get("/boards", response_model=list[BoardRead])
async def list_boards(session: Annotated[AsyncSession, Depends(get_session)]) -> list[Board]:
    result = await session.execute(select(Board).options(selectinload(Board.stages).selectinload(Stage.agent_config)).order_by(Board.created_at))
    return list(result.scalars().unique().all())


@router.post("/boards", response_model=BoardDetail, status_code=status.HTTP_201_CREATED)
async def create_board(session: Annotated[AsyncSession, Depends(get_session)], payload: BoardCreate) -> Board:
    board = Board(name=payload.name, description=payload.description)
    board.stages = [
        Stage(
            name="Urd",
            order=1,
            require_approval=True,
            agent_config=AgentConfig(
                system_prompt="You are Urd. Analyze the incoming card and produce a clear structured handoff.",
                model="gpt-4o",
                temperature=0.7,
                tool_allowlist=[],
            ),
        ),
        Stage(
            name="Verdandi",
            order=2,
            require_approval=True,
            agent_config=AgentConfig(
                system_prompt="You are Verdandi. Refine the active work using the approved handoff only.",
                model="gpt-4o",
                temperature=0.7,
                tool_allowlist=[],
            ),
        ),
        Stage(
            name="Skuld",
            order=3,
            require_approval=True,
            agent_config=AgentConfig(
                system_prompt="You are Skuld. Produce the final delivery handoff and highlight risks.",
                model="gpt-4o",
                temperature=0.7,
                tool_allowlist=[],
            ),
        ),
    ]
    session.add(board)
    await session.commit()
    await session.refresh(board)
    return await _get_board_or_404(session, board.id)


@router.get("/boards/{board_id}", response_model=BoardDetail)
async def get_board(board_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> Board:
    return await _get_board_or_404(session, board_id)


@router.put("/boards/{board_id}", response_model=BoardDetail)
async def update_board(board_id: str, payload: BoardUpdate, session: Annotated[AsyncSession, Depends(get_session)]) -> Board:
    board = await _get_board_or_404(session, board_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(board, field, value)
    await session.commit()
    return await _get_board_or_404(session, board_id)


@router.delete("/boards/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board(board_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> None:
    board = await _get_board_or_404(session, board_id)
    await session.delete(board)
    await session.commit()


@router.get("/boards/{board_id}/stages", response_model=list[StageRead])
async def list_stages(board_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> list[Stage]:
    await _get_board_or_404(session, board_id)
    result = await session.execute(select(Stage).where(Stage.board_id == board_id).options(selectinload(Stage.agent_config)).order_by(Stage.order))
    return list(result.scalars().all())


@router.post("/boards/{board_id}/stages", response_model=StageRead, status_code=status.HTTP_201_CREATED)
async def create_stage(board_id: str, payload: StageCreate, session: Annotated[AsyncSession, Depends(get_session)]) -> Stage:
    await _get_board_or_404(session, board_id)
    order = payload.order
    if order is None:
        result = await session.execute(select(func.max(Stage.order)).where(Stage.board_id == board_id))
        order = (result.scalar() or 0) + 1

    stage = Stage(board_id=board_id, name=payload.name, order=order, require_approval=payload.require_approval)
    stage.agent_config = AgentConfig(
        system_prompt=payload.system_prompt,
        model=payload.model,
        temperature=payload.temperature,
        tool_allowlist=payload.tool_allowlist,
    )
    session.add(stage)
    await session.commit()
    result = await session.execute(select(Stage).where(Stage.id == stage.id).options(selectinload(Stage.agent_config)))
    return result.scalar_one()


@router.put("/stages/{stage_id}", response_model=StageRead)
async def update_stage(stage_id: str, payload: StageUpdate, session: Annotated[AsyncSession, Depends(get_session)]) -> Stage:
    result = await session.execute(select(Stage).where(Stage.id == stage_id).options(selectinload(Stage.agent_config)))
    stage = result.scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")

    stage_fields = payload.model_dump(exclude_none=True, exclude={"system_prompt", "model", "temperature", "tool_allowlist"})
    for field, value in stage_fields.items():
        setattr(stage, field, value)

    if any(value is not None for value in [payload.system_prompt, payload.model, payload.temperature, payload.tool_allowlist]):
        if not stage.agent_config:
            stage.agent_config = AgentConfig(stage_id=stage.id)
        if payload.system_prompt is not None:
            stage.agent_config.system_prompt = payload.system_prompt
        if payload.model is not None:
            stage.agent_config.model = payload.model
        if payload.temperature is not None:
            stage.agent_config.temperature = payload.temperature
        if payload.tool_allowlist is not None:
            stage.agent_config.tool_allowlist = payload.tool_allowlist

    await session.commit()
    result = await session.execute(select(Stage).where(Stage.id == stage.id).options(selectinload(Stage.agent_config)))
    return result.scalar_one()


@router.delete("/stages/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stage(stage_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> None:
    result = await session.execute(select(Stage).where(Stage.id == stage_id))
    stage = result.scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    await session.delete(stage)
    await session.commit()


async def _get_board_or_404(session: AsyncSession, board_id: str) -> Board:
    result = await session.execute(
        select(Board)
        .where(Board.id == board_id)
        .options(
            selectinload(Board.stages).selectinload(Stage.agent_config),
            selectinload(Board.cards),
        )
    )
    board = result.scalar_one_or_none()
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")
    return board
