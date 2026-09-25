from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..card_preview import latest_practice, latest_recommendation
from ..database import get_session
from ..models import AgentConfig, Board, Card, Stage, StageTransition
from ..orchestrator.state_machine import TRANSITIONS, CardStatus
from ..workspace import validate_workspace_binding
from .auth import get_current_user


def _apply_workspace_fields(
    *, workspace_path: str | None = None, git_url: str | None = None
) -> tuple[str | None, str | None]:
    path = workspace_path.strip() if isinstance(workspace_path, str) else workspace_path
    url = git_url.strip() if isinstance(git_url, str) else git_url
    try:
        validate_workspace_binding(path or "", url or "")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return path, url


router = APIRouter(tags=["boards"], dependencies=[Depends(get_current_user)])


class AgentConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    system_prompt: str
    model: str
    llm_provider: str = ""
    temperature: float
    tool_allowlist: list[str]
    workspace_path: str = ""
    git_url: str = ""


class StageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    board_id: str
    name: str
    order: int
    lane: int = 0
    require_approval: bool
    confirm_writes: bool = False
    auto_start: bool = False
    agent_config: AgentConfigRead | None = None


class CardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    board_id: str
    title: str
    body: str
    external_id: str | None = None
    current_stage_id: str | None = None
    parent_card_id: str | None = None
    status: str
    recommendation: str | None = None
    recommendation_reason: str | None = None
    practice: bool = False

    @model_validator(mode="before")
    @classmethod
    def attach_latest_recommendation(cls, data: Any) -> Any:
        if not isinstance(data, Card):
            return data
        recommendation, reason = latest_recommendation(data)
        return {
            "id": data.id,
            "board_id": data.board_id,
            "title": data.title,
            "body": data.body,
            "external_id": data.external_id,
            "current_stage_id": data.current_stage_id,
            "parent_card_id": data.parent_card_id,
            "status": data.status,
            "recommendation": recommendation,
            "recommendation_reason": reason,
            "practice": latest_practice(data),
        }


class TransitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    board_id: str
    from_stage_id: str
    to_stage_id: str | None = None
    event: str
    condition_key: str
    condition_op: str
    condition_value: str
    order: int


class TransitionCreate(BaseModel):
    from_stage_id: str
    to_stage_id: str | None = None
    event: str = "approve"
    condition_key: str = ""
    condition_op: str = "eq"
    condition_value: str = ""
    order: int = 0


class TransitionUpdate(BaseModel):
    from_stage_id: str | None = None
    to_stage_id: str | None = None
    event: str | None = None
    condition_key: str | None = None
    condition_op: str | None = None
    condition_value: str | None = None
    order: int | None = None


class BoardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    workspace_path: str = ""
    git_url: str = ""
    created_at: Any
    updated_at: Any
    stages: list[StageRead] = []


class BoardDetail(BoardRead):
    cards: list[CardRead] = []
    transitions: list[TransitionRead] = []


class BoardCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    workspace_path: str = ""
    git_url: str = ""


class BoardUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    workspace_path: str | None = None
    git_url: str | None = None


class StageCreate(BaseModel):
    name: str = Field(min_length=1)
    order: int | None = None
    lane: int | None = None
    parallel: bool = False
    from_stage_id: str | None = None
    require_approval: bool = True
    confirm_writes: bool = False
    auto_start: bool = False
    system_prompt: str = (
        "You are the stage agent. Produce a concise handoff. "
        "If this stage has a human gate, recommend DECISION: approve or reject; a human must confirm."
    )
    model: str = "gpt-4o"
    llm_provider: str = ""
    temperature: float = 0.7
    tool_allowlist: list[str] = []
    workspace_path: str = ""
    git_url: str = ""


class StageUpdate(BaseModel):
    name: str | None = None
    order: int | None = None
    lane: int | None = None
    require_approval: bool | None = None
    confirm_writes: bool | None = None
    auto_start: bool | None = None
    system_prompt: str | None = None
    model: str | None = None
    llm_provider: str | None = None
    temperature: float | None = None
    tool_allowlist: list[str] | None = None
    workspace_path: str | None = None
    git_url: str | None = None


class StageReorder(BaseModel):
    stage_ids: list[str] = Field(min_length=1)


class CardStatusMachine(BaseModel):
    states: list[str]
    transitions: dict[str, list[str]]


VALID_EVENTS = {"approve", "reject", "auto"}
VALID_OPS = {"eq", "contains", "exists"}


@router.get("/boards", response_model=list[BoardRead])
async def list_boards(session: Annotated[AsyncSession, Depends(get_session)]) -> list[Board]:
    result = await session.execute(
        select(Board).options(selectinload(Board.stages).selectinload(Stage.agent_config)).order_by(Board.created_at)
    )
    return list(result.scalars().unique().all())


@router.post("/boards", response_model=BoardDetail, status_code=status.HTTP_201_CREATED)
async def create_board(session: Annotated[AsyncSession, Depends(get_session)], payload: BoardCreate) -> Board:
    path, url = _apply_workspace_fields(workspace_path=payload.workspace_path, git_url=payload.git_url)
    board = Board(
        name=payload.name,
        description=payload.description,
        workspace_path=path or "",
        git_url=url or "",
    )
    board.stages = [
        Stage(
            name="Urd",
            order=1,
            require_approval=True,
            agent_config=AgentConfig(
                system_prompt="You are Urd. Analyze the incoming card and produce a clear structured handoff. Recommend DECISION: approve or reject; a human must confirm.",
                model="",
                llm_provider="",
                temperature=0.7,
                tool_allowlist=[],
            ),
        ),
        Stage(
            name="Verdandi",
            order=2,
            require_approval=True,
            agent_config=AgentConfig(
                system_prompt="You are Verdandi. Do the approved work with tools (create tickets, update the card). Then hand off. Recommend DECISION: approve or reject; a human must confirm.",
                model="",
                llm_provider="",
                temperature=0.7,
                tool_allowlist=[],
            ),
        ),
        Stage(
            name="Skuld",
            order=3,
            require_approval=True,
            agent_config=AgentConfig(
                system_prompt="You are Skuld. Finish delivery with tools if anything is still undone, then produce the final handoff and highlight risks. Recommend DECISION: approve or reject; a human must confirm.",
                model="",
                llm_provider="",
                temperature=0.7,
                tool_allowlist=[],
            ),
        ),
    ]
    session.add(board)
    await session.flush()
    _seed_linear_transitions(session, board)
    first = board.stages[0]
    session.add(
        Card(
            board_id=board.id,
            title="Sample: first practice run",
            body=(
                "Open this card and press **Run**. Without a model connector you get a practice handoff — "
                "add DeepSeek, OpenAI, or Cursor in Settings for a real agent."
            ),
            status=CardStatus.IDLE,
            current_stage_id=first.id,
        )
    )
    await session.commit()
    return await _get_board_or_404(session, board.id)


@router.get("/boards/{board_id}", response_model=BoardDetail)
async def get_board(board_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> Board:
    return await _get_board_or_404(session, board_id)


@router.put("/boards/{board_id}", response_model=BoardDetail)
async def update_board(
    board_id: str, payload: BoardUpdate, session: Annotated[AsyncSession, Depends(get_session)]
) -> Board:
    board = await _get_board_or_404(session, board_id)
    data = payload.model_dump(exclude_none=True)
    if "workspace_path" in data or "git_url" in data:
        next_path = data.get("workspace_path", board.workspace_path)
        next_url = data.get("git_url", board.git_url)
        path, url = _apply_workspace_fields(workspace_path=next_path or "", git_url=next_url or "")
        data["workspace_path"] = path or ""
        data["git_url"] = url or ""
    for field, value in data.items():
        setattr(board, field, value)
    await session.commit()
    return await _get_board_or_404(session, board_id)


@router.delete("/boards/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board(board_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> None:
    board = await _get_board_or_404(session, board_id)
    await session.delete(board)
    await session.commit()


@router.get("/orchestration/card-status", response_model=CardStatusMachine)
async def card_status_machine() -> CardStatusMachine:
    return CardStatusMachine(
        states=[status.value for status in CardStatus],
        transitions={
            source.value: sorted(target.value for target in targets) for source, targets in TRANSITIONS.items()
        },
    )


@router.get("/boards/{board_id}/stages", response_model=list[StageRead])
async def list_stages(board_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> list[Stage]:
    await _get_board_or_404(session, board_id)
    result = await session.execute(
        select(Stage).where(Stage.board_id == board_id).options(selectinload(Stage.agent_config)).order_by(Stage.order)
    )
    return list(result.scalars().all())


@router.post("/boards/{board_id}/stages", response_model=StageRead, status_code=status.HTTP_201_CREATED)
async def create_stage(
    board_id: str, payload: StageCreate, session: Annotated[AsyncSession, Depends(get_session)]
) -> Stage:
    board = await _get_board_or_404(session, board_id)
    if payload.parallel:
        if not payload.from_stage_id:
            raise HTTPException(status_code=400, detail="from_stage_id is required to add a parallel stage")
        source = next((stage for stage in board.stages if stage.id == payload.from_stage_id), None)
        if not source:
            raise HTTPException(status_code=400, detail="from_stage_id is not on this board")
        order, lane = _parallel_placement(board, source)
    else:
        order = payload.order
        if order is None:
            result = await session.execute(select(func.max(Stage.order)).where(Stage.board_id == board_id))
            order = (result.scalar() or 0) + 1
        lane = payload.lane if payload.lane is not None else 0

    stage = Stage(
        board_id=board_id,
        name=payload.name,
        order=order,
        lane=lane,
        require_approval=payload.require_approval,
        confirm_writes=payload.confirm_writes,
        auto_start=payload.auto_start,
    )
    agent_path, agent_url = _apply_workspace_fields(workspace_path=payload.workspace_path, git_url=payload.git_url)
    stage.agent_config = AgentConfig(
        system_prompt=payload.system_prompt,
        model=payload.model,
        llm_provider=payload.llm_provider,
        temperature=payload.temperature,
        tool_allowlist=payload.tool_allowlist,
        workspace_path=agent_path or "",
        git_url=agent_url or "",
    )
    session.add(stage)
    await session.flush()
    if payload.parallel and payload.from_stage_id:
        session.add(
            StageTransition(
                board_id=board_id,
                from_stage_id=payload.from_stage_id,
                to_stage_id=stage.id,
                event="approve" if source.require_approval else "auto",
            )
        )
    else:
        await _attach_new_stage_transition(session, board_id, stage)
    await session.commit()
    result = await session.execute(select(Stage).where(Stage.id == stage.id).options(selectinload(Stage.agent_config)))
    return result.scalar_one()


@router.put("/stages/{stage_id}", response_model=StageRead)
async def update_stage(
    stage_id: str, payload: StageUpdate, session: Annotated[AsyncSession, Depends(get_session)]
) -> Stage:
    result = await session.execute(select(Stage).where(Stage.id == stage_id).options(selectinload(Stage.agent_config)))
    stage = result.scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")

    stage_fields = payload.model_dump(
        exclude_none=True,
        exclude={
            "system_prompt",
            "model",
            "llm_provider",
            "temperature",
            "tool_allowlist",
            "workspace_path",
            "git_url",
        },
    )
    for field, value in stage_fields.items():
        setattr(stage, field, value)

    if any(
        value is not None
        for value in [
            payload.system_prompt,
            payload.model,
            payload.llm_provider,
            payload.temperature,
            payload.tool_allowlist,
            payload.workspace_path,
            payload.git_url,
        ]
    ):
        if not stage.agent_config:
            stage.agent_config = AgentConfig(stage_id=stage.id)
        if payload.system_prompt is not None:
            stage.agent_config.system_prompt = payload.system_prompt
        if payload.model is not None:
            stage.agent_config.model = payload.model
        if payload.llm_provider is not None:
            stage.agent_config.llm_provider = payload.llm_provider
        if payload.temperature is not None:
            stage.agent_config.temperature = payload.temperature
        if payload.tool_allowlist is not None:
            stage.agent_config.tool_allowlist = payload.tool_allowlist
        if payload.workspace_path is not None or payload.git_url is not None:
            next_path = (
                payload.workspace_path if payload.workspace_path is not None else stage.agent_config.workspace_path
            )
            next_url = payload.git_url if payload.git_url is not None else stage.agent_config.git_url
            agent_path, agent_url = _apply_workspace_fields(workspace_path=next_path or "", git_url=next_url or "")
            stage.agent_config.workspace_path = agent_path or ""
            stage.agent_config.git_url = agent_url or ""

    await session.commit()
    if payload.auto_start is True:
        from ..orchestrator.auto_start import pickup_idle_cards_for_stage

        await pickup_idle_cards_for_stage(session, stage.id)
    result = await session.execute(select(Stage).where(Stage.id == stage.id).options(selectinload(Stage.agent_config)))
    return result.scalar_one()


@router.put("/boards/{board_id}/stages/reorder", response_model=list[StageRead])
async def reorder_stages(
    board_id: str, payload: StageReorder, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[Stage]:
    await _get_board_or_404(session, board_id)
    result = await session.execute(
        select(Stage).where(Stage.board_id == board_id).options(selectinload(Stage.agent_config))
    )
    stages = list(result.scalars().unique().all())
    existing_ids = {stage.id for stage in stages}
    requested = payload.stage_ids
    if len(requested) != len(set(requested)) or set(requested) != existing_ids:
        raise HTTPException(status_code=400, detail="stage_ids must list every stage on this board exactly once")
    order_by_id = {stage_id: index for index, stage_id in enumerate(requested, start=1)}
    for stage in stages:
        stage.order = order_by_id[stage.id]
    await session.commit()
    result = await session.execute(
        select(Stage).where(Stage.board_id == board_id).options(selectinload(Stage.agent_config)).order_by(Stage.order)
    )
    return list(result.scalars().all())


@router.delete("/stages/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stage(stage_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> None:
    result = await session.execute(select(Stage).where(Stage.id == stage_id))
    stage = result.scalar_one_or_none()
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    remaining = await session.scalar(select(func.count()).select_from(Stage).where(Stage.board_id == stage.board_id))
    if remaining is not None and remaining <= 1:
        raise HTTPException(status_code=409, detail="A board must keep at least one stage")
    cards_here = await session.scalar(select(func.count()).select_from(Card).where(Card.current_stage_id == stage_id))
    if cards_here:
        raise HTTPException(status_code=409, detail="Cannot delete a stage that still has cards")
    await session.delete(stage)
    await session.commit()


@router.post("/boards/{board_id}/transitions", response_model=TransitionRead, status_code=status.HTTP_201_CREATED)
async def create_transition(
    board_id: str, payload: TransitionCreate, session: Annotated[AsyncSession, Depends(get_session)]
) -> StageTransition:
    board = await _get_board_or_404(session, board_id)
    _validate_transition_payload(
        board,
        payload.from_stage_id,
        payload.to_stage_id,
        payload.event,
        payload.condition_op,
        payload.condition_key,
        payload.condition_value,
    )
    edge = StageTransition(
        board_id=board_id,
        from_stage_id=payload.from_stage_id,
        to_stage_id=payload.to_stage_id,
        event=payload.event,
        condition_key=payload.condition_key,
        condition_op=payload.condition_op,
        condition_value=payload.condition_value,
        order=payload.order,
    )
    session.add(edge)
    await session.commit()
    await session.refresh(edge)
    return edge


@router.put("/transitions/{transition_id}", response_model=TransitionRead)
async def update_transition(
    transition_id: str, payload: TransitionUpdate, session: Annotated[AsyncSession, Depends(get_session)]
) -> StageTransition:
    result = await session.execute(select(StageTransition).where(StageTransition.id == transition_id))
    edge = result.scalar_one_or_none()
    if not edge:
        raise HTTPException(status_code=404, detail="Transition not found")
    board = await _get_board_or_404(session, edge.board_id)
    updates = payload.model_dump(exclude_unset=True)
    from_id = updates.get("from_stage_id", edge.from_stage_id)
    to_id = updates.get("to_stage_id", edge.to_stage_id)
    event = updates.get("event", edge.event)
    op = updates.get("condition_op", edge.condition_op)
    key = updates.get("condition_key", edge.condition_key)
    value = updates.get("condition_value", edge.condition_value)
    _validate_transition_payload(board, from_id, to_id, event, op, key, value)
    for field, value in updates.items():
        setattr(edge, field, value)
    await session.commit()
    await session.refresh(edge)
    return edge


@router.delete("/transitions/{transition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transition(transition_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> None:
    result = await session.execute(select(StageTransition).where(StageTransition.id == transition_id))
    edge = result.scalar_one_or_none()
    if not edge:
        raise HTTPException(status_code=404, detail="Transition not found")
    await session.delete(edge)
    await session.commit()


async def _get_board_or_404(session: AsyncSession, board_id: str) -> Board:
    board = await _load_board(session, board_id)
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")
    return board


async def _load_board(session: AsyncSession, board_id: str) -> Board | None:
    result = await session.execute(
        select(Board)
        .where(Board.id == board_id)
        .options(
            selectinload(Board.stages).selectinload(Stage.agent_config),
            selectinload(Board.cards).selectinload(Card.runs),
            selectinload(Board.transitions),
        )
    )
    return result.scalar_one_or_none()


def _parallel_placement(board: Board, source: Stage) -> tuple[int, int]:
    outgoing_ids = {
        edge.to_stage_id
        for edge in board.transitions
        if edge.from_stage_id == source.id
        and edge.to_stage_id
        and not edge.condition_key.strip()
        and edge.event in {"approve", "auto"}
    }
    targets = [stage for stage in board.stages if stage.id in outgoing_ids]
    forward = [stage for stage in targets if stage.order > source.order]
    order = min(stage.order for stage in forward) if forward else source.order + 1
    lanes = [stage.lane for stage in board.stages if stage.order == order]
    lane = (max(lanes) + 1) if lanes else 0
    return order, lane


def _seed_linear_transitions(session: AsyncSession, board: Board) -> None:
    ordered = sorted(board.stages, key=lambda stage: stage.order)
    for index, stage in enumerate(ordered):
        nxt = ordered[index + 1] if index + 1 < len(ordered) else None
        session.add(
            StageTransition(
                board_id=board.id,
                from_stage_id=stage.id,
                to_stage_id=nxt.id if nxt else None,
                event="approve" if stage.require_approval else "auto",
                order=index,
            )
        )


async def _attach_new_stage_transition(session: AsyncSession, board_id: str, stage: Stage) -> None:
    previous = (
        (
            await session.execute(
                select(Stage).where(Stage.board_id == board_id, Stage.id != stage.id).order_by(Stage.order.desc())
            )
        )
        .scalars()
        .first()
    )
    event = "approve" if stage.require_approval else "auto"
    if previous:
        result = await session.execute(
            select(StageTransition).where(
                StageTransition.board_id == board_id,
                StageTransition.from_stage_id == previous.id,
                StageTransition.to_stage_id.is_(None),
                StageTransition.event.in_(("approve", "auto")),
            )
        )
        retargeted = False
        for edge in result.scalars():
            edge.to_stage_id = stage.id
            retargeted = True
        if not retargeted:
            session.add(
                StageTransition(
                    board_id=board_id,
                    from_stage_id=previous.id,
                    to_stage_id=stage.id,
                    event="approve" if previous.require_approval else "auto",
                )
            )
    session.add(
        StageTransition(
            board_id=board_id,
            from_stage_id=stage.id,
            to_stage_id=None,
            event=event,
        )
    )


def _validate_transition_payload(
    board: Board,
    from_stage_id: str,
    to_stage_id: str | None,
    event: str,
    condition_op: str,
    condition_key: str = "",
    condition_value: str = "",
) -> None:
    stage_ids = {stage.id for stage in board.stages}
    if from_stage_id not in stage_ids:
        raise HTTPException(status_code=400, detail="from_stage_id is not on this board")
    if to_stage_id is not None and to_stage_id not in stage_ids:
        raise HTTPException(status_code=400, detail="to_stage_id is not on this board")
    if event not in VALID_EVENTS:
        raise HTTPException(status_code=400, detail="event must be approve, reject, or auto")
    if condition_op not in VALID_OPS:
        raise HTTPException(status_code=400, detail="condition_op must be eq, contains, or exists")
    if condition_op == "contains" and condition_key.strip() and not condition_value.strip():
        raise HTTPException(status_code=400, detail="contains conditions need a non-empty value")
