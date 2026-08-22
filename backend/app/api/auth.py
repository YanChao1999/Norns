from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel

from ..config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class SessionUser(BaseModel):
    username: str


class SessionSerializer:
    def __init__(self) -> None:
        settings = get_settings()
        self._serializer = URLSafeSerializer(settings.secret_key, salt="norns-session")
        self.cookie_name = settings.session_cookie_name
        self.max_age = settings.session_max_age

    def dumps(self, username: str) -> str:
        return self._serializer.dumps({"username": username})

    def loads(self, value: str) -> dict:
        return self._serializer.loads(value)


serializer = SessionSerializer()


def get_current_user(session_cookie: Annotated[str | None, Cookie(alias=serializer.cookie_name)] = None) -> SessionUser:
    if not session_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = serializer.loads(session_cookie)
    except BadSignature as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc
    return SessionUser(username=payload["username"])


@router.post("/login", response_model=SessionUser)
async def login(payload: LoginRequest, response: Response) -> SessionUser:
    settings = get_settings()
    if payload.username != settings.admin_username or payload.password != settings.admin_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    cookie_value = serializer.dumps(payload.username)
    response.set_cookie(
        serializer.cookie_name,
        cookie_value,
        httponly=True,
        max_age=serializer.max_age,
        samesite="lax",
    )
    return SessionUser(username=payload.username)


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(serializer.cookie_name)
    return {"message": "Logged out"}


@router.get("/me", response_model=SessionUser)
async def me(current_user: Annotated[SessionUser, Depends(get_current_user)]) -> SessionUser:
    return current_user
