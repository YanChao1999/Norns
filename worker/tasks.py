from __future__ import annotations

from backend.app.agents.runner import run_stage


async def run_stage_task(ctx: dict, card_id: str, stage_id: str, run_id: str) -> None:
    _ = ctx
    await run_stage(card_id, stage_id, run_id)
