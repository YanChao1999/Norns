from __future__ import annotations

import asyncio

from cursor_sdk import AsyncAgent, AsyncClient, CloudAgentOptions, CloudRepository

DEFAULT_CURSOR_MODEL = "auto"


def _normalize_model_id(model: str) -> str | None:
    model_id = str(model or "").strip()
    if not model_id or model_id.lower() in {"auto", "default"}:
        return None
    return model_id


async def list_cursor_models(api_key: str, *, base_url: str = "") -> list[str]:
    """List Cursor models via cursor-sdk. ``base_url`` is ignored (SDK owns the endpoint)."""
    del base_url  # kept for call-site compatibility with connector config
    key = api_key.strip()
    if not key:
        return [DEFAULT_CURSOR_MODEL]

    client = AsyncClient(auth_token=key)
    try:
        items = await client.list_models(api_key=key)
    finally:
        await client.aclose()

    models: list[str] = []
    for item in items:
        model_id = str(getattr(item, "id", "") or "").strip()
        if model_id and model_id not in models:
            models.append(model_id)
    if DEFAULT_CURSOR_MODEL not in models:
        models.insert(0, DEFAULT_CURSOR_MODEL)
    return models


async def run_cursor_cloud_agent(
    *,
    api_key: str,
    prompt: str,
    model: str = DEFAULT_CURSOR_MODEL,
    base_url: str = "",
    repo_url: str = "",
    poll_seconds: float = 2.0,
    timeout_seconds: float = 600.0,
) -> str:
    """Run a Cursor Cloud Agent for a Norns stage using cursor-sdk only."""
    del base_url, poll_seconds  # REST polling / host override are unused with the SDK
    key = api_key.strip()
    if not key:
        raise ValueError("Cursor API key is required")

    model_id = _normalize_model_id(model)
    repos: list[CloudRepository] = []
    repo = str(repo_url or "").strip()
    if repo:
        repos.append(CloudRepository(url=repo))

    client = AsyncClient(auth_token=key)
    agent = None
    try:
        agent = await AsyncAgent.create(
            client=client,
            model=model_id,
            api_key=key,
            name="Norns stage run",
            cloud=CloudAgentOptions(repos=repos),
        )
        run = await agent.send(prompt)
        await asyncio.wait_for(run.wait(), timeout=timeout_seconds)
        text = (await run.text() or "").strip()
        if not text:
            raise RuntimeError("Cursor SDK agent finished with an empty result")
        return text
    finally:
        if agent is not None:
            close = getattr(agent, "close", None) or getattr(agent, "aclose", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
        await client.aclose()
