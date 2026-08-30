from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Mapping
from typing import Any

from cursor_sdk import (
    AgentOptions,
    AsyncAgent,
    AsyncClient,
    CloudAgentOptions,
    CloudRepository,
    HttpMcpServerConfig,
    LocalAgentOptions,
    StdioMcpServerConfig,
)

DEFAULT_CURSOR_MODEL = "auto"


def _model_for_sdk(model: str) -> str:
    model_id = str(model or "").strip()
    if not model_id or model_id.lower() in {"default"}:
        return DEFAULT_CURSOR_MODEL
    return model_id


async def list_cursor_models(api_key: str, *, base_url: str = "") -> list[str]:
    """List Cursor models via cursor-sdk (bridge + API key). ``base_url`` is unused."""
    del base_url
    key = api_key.strip()
    if not key:
        return [DEFAULT_CURSOR_MODEL]

    async with await AsyncClient.launch_bridge(workspace=_bridge_workspace()) as client:
        items = await client.list_models(api_key=key)

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
    timeout_seconds: float = 1200.0,
    mcp_servers: Mapping[str, Mapping[str, Any]] | None = None,
    workspace_path: str = "",
) -> str:
    """Run a Cursor agent for a Norns stage using cursor-sdk only."""
    del base_url, poll_seconds
    key = api_key.strip()
    if not key:
        raise ValueError("Cursor API key is required")

    model_id = _model_for_sdk(model)
    local_root = str(workspace_path or "").strip()
    use_local = bool(local_root) and _is_git_dir(local_root)
    bridge_root = local_root if use_local else _bridge_workspace()
    repos: list[CloudRepository] = []
    repo = str(repo_url or "").strip()
    if repo and not use_local:
        repos.append(CloudRepository(url=repo))
    options = AgentOptions(mcp_servers=_sdk_mcp_servers(mcp_servers)) if mcp_servers else None

    async with await AsyncClient.launch_bridge(workspace=bridge_root) as client:
        create_kwargs: dict[str, Any] = {
            "client": client,
            "model": model_id,
            "api_key": key,
            "name": "Norns stage run",
        }
        if use_local:
            create_kwargs["local"] = LocalAgentOptions(cwd=local_root)
        else:
            create_kwargs["cloud"] = CloudAgentOptions(repos=repos)
        agent = await (AsyncAgent.create(options, **create_kwargs) if options else AsyncAgent.create(**create_kwargs))
        try:
            run = await agent.send(prompt)
            try:
                await asyncio.wait_for(run.wait(), timeout=timeout_seconds)
            except TimeoutError:
                raise RuntimeError(
                    f"Cursor cloud agent did not finish within {int(timeout_seconds)}s. "
                    "Rerun this stage, or set the stage LLM to DeepSeek/OpenAI."
                ) from None
            text = (await run.text() or "").strip()
            if not text:
                raise RuntimeError("Cursor SDK agent finished with an empty result")
            return text
        finally:
            close = getattr(agent, "close", None) or getattr(agent, "aclose", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    await result


def _sdk_mcp_servers(servers: Mapping[str, Mapping[str, Any]] | None) -> dict[str, Any] | None:
    if not servers:
        return None
    converted: dict[str, Any] = {}
    for name, config in servers.items():
        url = str(config.get("url") or "").strip()
        if url:
            converted[name] = HttpMcpServerConfig(url=url, type=str(config.get("type") or "http"))
            continue
        command = str(config.get("command") or "").strip()
        if not command:
            continue
        converted[name] = StdioMcpServerConfig(
            command=command,
            args=list(config.get("args") or []),
            env=dict(config.get("env") or {}),
            cwd=str(config.get("cwd") or "") or None,
        )
    return converted or None


def _is_git_dir(path: str) -> bool:
    from pathlib import Path

    root = Path(path)
    return root.is_dir() and (root / ".git").exists()


def _bridge_workspace() -> str:
    """Disposable workspace for the SDK bridge (cloud agents do not need a real repo checkout)."""
    return tempfile.mkdtemp(prefix="norns-cursor-bridge-")
