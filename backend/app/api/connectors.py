from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Connector, ConnectorType
from .auth import get_current_user

router = APIRouter(prefix="/connectors", tags=["connectors"], dependencies=[Depends(get_current_user)])


class ConnectorCreate(BaseModel):
    name: str = Field(min_length=1)
    connector_type: ConnectorType
    config: dict
    is_active: bool = True


class ConnectorUpdate(BaseModel):
    name: str | None = None
    connector_type: ConnectorType | None = None
    config: dict | None = None
    is_active: bool | None = None


class ConnectorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    connector_type: ConnectorType
    is_active: bool
    config_keys: list[str]


@router.get("", response_model=list[ConnectorRead])
async def list_connectors(session: Annotated[AsyncSession, Depends(get_session)]) -> list[Connector]:
    result = await session.execute(select(Connector).order_by(Connector.name))
    return list(result.scalars().all())


@router.post("", response_model=ConnectorRead, status_code=status.HTTP_201_CREATED)
async def create_connector(payload: ConnectorCreate, session: Annotated[AsyncSession, Depends(get_session)]) -> Connector:
    connector = Connector(name=payload.name, connector_type=payload.connector_type, is_active=payload.is_active, encrypted_config=b"")
    connector.set_config(payload.config)
    session.add(connector)
    await session.commit()
    await session.refresh(connector)
    return connector


@router.put("/{connector_id}", response_model=ConnectorRead)
async def update_connector(connector_id: str, payload: ConnectorUpdate, session: Annotated[AsyncSession, Depends(get_session)]) -> Connector:
    connector = await session.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    updates = payload.model_dump(exclude_none=True, exclude={"config"})
    for field, value in updates.items():
        setattr(connector, field, value)
    if payload.config is not None:
        connector.set_config(payload.config)
    await session.commit()
    await session.refresh(connector)
    return connector


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(connector_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> None:
    connector = await session.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    await session.delete(connector)
    await session.commit()
