from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..proxy_env import (
    httpx_trust_env,
    proxy_env_snapshot,
    set_use_system_proxy,
    use_system_proxy,
)
from .auth import SessionUser, get_current_user

router = APIRouter(prefix="/preferences", tags=["preferences"])


class PreferencesOut(BaseModel):
    use_system_proxy: bool
    proxy_env_detected: bool
    proxy_env: dict[str, str] = Field(default_factory=dict)


class PreferencesUpdate(BaseModel):
    use_system_proxy: bool


@router.get("", response_model=PreferencesOut)
async def get_preferences(_: Annotated[SessionUser, Depends(get_current_user)]) -> PreferencesOut:
    snapshot = proxy_env_snapshot()
    return PreferencesOut(
        use_system_proxy=use_system_proxy(),
        proxy_env_detected=bool(snapshot),
        proxy_env=snapshot,
    )


@router.put("", response_model=PreferencesOut)
async def update_preferences(
    payload: PreferencesUpdate,
    _: Annotated[SessionUser, Depends(get_current_user)],
) -> PreferencesOut:
    set_use_system_proxy(payload.use_system_proxy, persist=True)
    # Touch trust path so socks normalization runs when enabling proxy.
    httpx_trust_env()
    snapshot = proxy_env_snapshot()
    return PreferencesOut(
        use_system_proxy=use_system_proxy(),
        proxy_env_detected=bool(snapshot),
        proxy_env=snapshot,
    )
