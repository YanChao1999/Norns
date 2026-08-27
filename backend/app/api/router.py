from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..connector_config import llm_is_configured
from ..database import get_session
from ..models import Connector, Stage
from ..workspace import resolve_workspace, serialize_workspace
from .auth import get_current_user
from .auth import router as auth_router
from .boards import router as boards_router
from .cards import router as cards_router
from .connectors import router as connectors_router
from .plugins import router as plugins_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(boards_router)
api_router.include_router(cards_router)
api_router.include_router(connectors_router)
api_router.include_router(plugins_router)


@api_router.get("/workspace", tags=["workspace"], dependencies=[Depends(get_current_user)])
async def workspace(
    session: Annotated[AsyncSession, Depends(get_session)],
    board_id: Annotated[str | None, Query()] = None,
    stage_id: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    result = await session.execute(select(Connector).where(Connector.is_active.is_(True)))
    connectors = list(result.scalars().all())
    board = None
    agent = None
    if stage_id:
        stage_result = await session.execute(
            select(Stage)
            .where(Stage.id == stage_id)
            .options(selectinload(Stage.agent_config), selectinload(Stage.board))
        )
        stage = stage_result.scalar_one_or_none()
        if stage is not None:
            agent = stage.agent_config
            board = stage.board
            if board_id and stage.board_id != board_id:
                board = None
                agent = None
    elif board_id:
        from ..models import Board

        board = await session.get(Board, board_id)
    found = resolve_workspace(connectors, agent=agent, board=board)
    return serialize_workspace(found)


@api_router.get("/health", tags=["health"])
async def health(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, object]:
    settings = get_settings()
    result = await session.execute(select(Connector).where(Connector.is_active.is_(True)))
    return {
        "status": "ok",
        "openai_configured": llm_is_configured(list(result.scalars().all()), settings),
    }
