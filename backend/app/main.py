from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.router import api_router
from .config import get_settings
from .database import AsyncSessionLocal, init_db
from .orchestrator.recovery import recover_stale_runs
from .ui_assets import discover_ui_dir

logger = logging.getLogger("norns")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.environment.strip().lower() != "production" and settings.admin_password == "admin":
        logger.warning(
            "ADMIN_PASSWORD is the default value. Set NORNS_ENV=production and a unique password before sharing this instance."
        )
    if settings.auto_create_tables:
        await init_db()
    async with AsyncSessionLocal() as session:
        recovered = await recover_stale_runs(session, older_than_seconds=settings.stale_run_seconds)
        if recovered:
            logger.warning("Recovered %s stale stage run(s).", recovered)
    yield


def _mount_packaged_ui(application: FastAPI) -> None:
    ui_dir = discover_ui_dir()
    if ui_dir is None:
        return
    application.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")


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
_mount_packaged_ui(app)
