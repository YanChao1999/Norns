from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.router import api_router
from .config import get_settings
from .database import init_db

logger = logging.getLogger("norns")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.admin_password == "admin":
        logger.warning("ADMIN_PASSWORD is the default value. Change it before any shared deployment.")
    if settings.auto_create_tables:
        await init_db()
    yield


app = FastAPI(title="Norns", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
