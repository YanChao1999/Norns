from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from arq import create_pool
from arq.connections import RedisSettings

from ..config import get_settings

logger = logging.getLogger("norns")


class EnqueueError(Exception):
    """Raised when a stage run cannot be queued."""


_pool = None
_inline_tasks: set[asyncio.Task] = set()


async def _get_pool():
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


def _spawn_inline_run(card_id: str, stage_id: str, run_id: str) -> None:
    """Keep a strong reference so the inline job is not garbage-collected mid-run."""
    from ..agents.runner import run_stage

    task = asyncio.create_task(run_stage(card_id, stage_id, run_id), name=f"norns-run-{run_id}")
    _inline_tasks.add(task)

    def _on_done(done: asyncio.Task) -> None:
        _inline_tasks.discard(done)
        if done.cancelled():
            return
        exc = done.exception()
        if exc is not None:
            logger.exception("Inline stage run failed card=%s stage=%s", card_id, stage_id, exc_info=exc)

    task.add_done_callback(_on_done)


async def enqueue_stage_run(card_id: str, stage_id: str, run_id: str | None = None) -> str:
    resolved_run_id = run_id or str(uuid4())
    settings = get_settings()
    if settings.queue_backend == "inline":
        _spawn_inline_run(card_id, stage_id, resolved_run_id)
        return resolved_run_id
    try:
        redis = await _get_pool()
        await redis.enqueue_job("run_stage_task", card_id=card_id, stage_id=stage_id, run_id=resolved_run_id)
    except Exception as exc:
        raise EnqueueError("Failed to enqueue stage run") from exc
    return resolved_run_id
