from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..connector_config import llm_is_configured
from ..database import get_session
from ..models import Connector
from .auth import router as auth_router
from .boards import router as boards_router
from .cards import router as cards_router
from .connectors import router as connectors_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(boards_router)
api_router.include_router(cards_router)
api_router.include_router(connectors_router)


@api_router.get("/health", tags=["health"])
async def health(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, object]:
    settings = get_settings()
    result = await session.execute(select(Connector).where(Connector.is_active.is_(True)))
    return {
        "status": "ok",
        "openai_configured": llm_is_configured(list(result.scalars().all()), settings),
    }
