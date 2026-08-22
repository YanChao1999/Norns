from __future__ import annotations

from uuid import uuid4

from arq import create_pool
from arq.connections import RedisSettings

from ..config import get_settings


async def enqueue_stage_run(card_id: str, stage_id: str, run_id: str | None = None) -> str:
    settings = get_settings()
    resolved_run_id = run_id or str(uuid4())
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    await redis.enqueue_job("run_stage_task", card_id=card_id, stage_id=stage_id, run_id=resolved_run_id)
    await redis.close()
    return resolved_run_id
