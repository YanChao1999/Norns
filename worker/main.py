from __future__ import annotations

from arq.connections import RedisSettings

from backend.app.config import get_settings

from .tasks import run_stage_task

settings = get_settings()


class WorkerSettings:
    functions = [run_stage_task]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
