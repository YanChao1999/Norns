from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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


def _discover_ui_dir() -> Path | None:
    here = Path(__file__).resolve()
    roots = [
        here.parents[2] / "norns" / "web",
        here.parents[2] / "frontend" / "dist",
        here.parent / "web",
    ]
    try:
        import norns as norns_pkg

        roots.insert(0, Path(norns_pkg.__file__).resolve().parent / "web")
    except ImportError:
        pass
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "index.html").is_file():
            return resolved
    return None


def _mount_packaged_ui(application: FastAPI) -> None:
    ui_dir = _discover_ui_dir()
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
