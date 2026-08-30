from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..connector_config import (
    LLM_CONNECTOR_TYPES,
    LLM_LABELS,
    credentials_for_provider,
    fetch_all_llm_model_catalogs,
    fetch_llm_model_catalog,
    merge_connector_config,
)
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
    public_config: dict[str, str] = Field(default_factory=dict)


class LlmModelEntryRead(BaseModel):
    id: str
    provider: str
    label: str
    usable: bool
    source: str


class LlmModelCatalogRead(BaseModel):
    provider: str
    default_model: str
    models: list[str]
    source: str
    error: str = ""
    entries: list[LlmModelEntryRead] = Field(default_factory=list)


@router.get("", response_model=list[ConnectorRead])
async def list_connectors(session: Annotated[AsyncSession, Depends(get_session)]) -> list[Connector]:
    result = await session.execute(select(Connector).order_by(Connector.name))
    return list(result.scalars().all())


@router.get("/llm-models", response_model=LlmModelCatalogRead)
async def list_llm_models(
    session: Annotated[AsyncSession, Depends(get_session)],
    provider: str | None = None,
) -> LlmModelCatalogRead:
    settings = get_settings()
    result = await session.execute(select(Connector).where(Connector.is_active.is_(True)))
    connectors = list(result.scalars().all())
    if provider and str(provider).strip():
        catalog = await fetch_llm_model_catalog(credentials_for_provider(connectors, settings, provider))
    else:
        catalog = await fetch_all_llm_model_catalogs(connectors, settings)
    return LlmModelCatalogRead(
        provider=catalog.provider,
        default_model=catalog.default_model,
        models=catalog.models,
        source=catalog.source,
        error=catalog.error,
        entries=[
            LlmModelEntryRead(
                id=entry.id,
                provider=entry.provider,
                label=entry.label,
                usable=entry.usable,
                source=entry.source,
            )
            for entry in catalog.entries
        ],
    )


@router.post("", response_model=ConnectorRead, status_code=status.HTTP_201_CREATED)
async def create_connector(
    payload: ConnectorCreate, session: Annotated[AsyncSession, Depends(get_session)]
) -> Connector:
    connector = Connector(
        name=payload.name, connector_type=payload.connector_type, is_active=payload.is_active, encrypted_config=b""
    )
    connector.set_config(payload.config)
    _validate_llm_key(connector)
    session.add(connector)
    await session.commit()
    await session.refresh(connector)
    return connector


@router.put("/{connector_id}", response_model=ConnectorRead)
async def update_connector(
    connector_id: str, payload: ConnectorUpdate, session: Annotated[AsyncSession, Depends(get_session)]
) -> Connector:
    connector = await session.get(Connector, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    updates = payload.model_dump(exclude_none=True, exclude={"config"})
    for field, value in updates.items():
        setattr(connector, field, value)
    if payload.config is not None:
        connector.set_config(merge_connector_config(connector.get_config(), payload.config))
    _validate_llm_key(connector)
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


def _validate_llm_key(connector: Connector) -> None:
    if connector.connector_type not in LLM_CONNECTOR_TYPES:
        return
    key = str(connector.get_config().get("api_key") or "").strip()
    if not key:
        label = LLM_LABELS.get(connector.connector_type, connector.connector_type.value)
        raise HTTPException(status_code=400, detail=f"{label} connector needs an API key")
