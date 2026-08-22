from __future__ import annotations

import asyncio
from uuid import uuid4

from arq import create_pool
from arq.connections import RedisSettings

from ..config import get_settings


class EnqueueError(Exception):
    """Raised when a stage run cannot be queued."""


_pool = None


async def _get_pool():
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def enqueue_stage_run(card_id: str, stage_id: str, run_id: str | None = None) -> str:
    resolved_run_id = run_id or str(uuid4())
    settings = get_settings()
    if settings.queue_backend == "inline":
        from ..agents.runner import run_stage

        asyncio.create_task(run_stage(card_id, stage_id, resolved_run_id))
        return resolved_run_id
    try:
        redis = await _get_pool()
        await redis.enqueue_job("run_stage_task", card_id=card_id, stage_id=stage_id, run_id=resolved_run_id)
    except Exception as exc:
        raise EnqueueError("Failed to enqueue stage run") from exc
    return resolved_run_id
