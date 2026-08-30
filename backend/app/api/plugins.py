from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Connector
from ..plugins.catalog import load_plugin_catalog
from .auth import get_current_user

router = APIRouter(prefix="/plugins", tags=["plugins"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[dict[str, Any]])
async def list_plugins(session: Annotated[AsyncSession, Depends(get_session)]) -> list[dict[str, Any]]:
    result = await session.execute(select(Connector).where(Connector.is_active.is_(True)))
    connectors = list(result.scalars().all())
    return load_plugin_catalog(connectors).summaries(connectors)
