from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
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

# OpenAI / DeepSeek chat ids Cursor Cloud Agents reject (keep aligned with connector_config).
_NON_CURSOR_CHAT_MODEL_IDS = frozenset(
    {
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-4.1-mini",
        "o3-mini",
        "o4-mini",
        "gpt-4",
        "gpt-3.5-turbo",
        "chatgpt-4o-latest",
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash-vision-exp",
        "deepseek-chat",
        "deepseek-reasoner",
    }
)


@dataclass(frozen=True, slots=True)
class CursorModelInfo:
    id: str
    display_name: str = ""


def _model_for_sdk(model: str) -> str:
    model_id = str(model or "").strip()
    lower = model_id.lower()
    if not model_id or lower in {"default"} or lower.startswith("deepseek") or lower in _NON_CURSOR_CHAT_MODEL_IDS:
        return DEFAULT_CURSOR_MODEL
    return model_id


def _cursor_models_url(base_url: str = "") -> str:
    root = str(base_url or "").strip().rstrip("/")
    if not root:
        return "https://api.cursor.com/v1/models"
    if root.endswith("/models"):
        return root
    if root.endswith("/v1"):
        return f"{root}/models"
    if "api.cursor.com" in root:
        return "https://api.cursor.com/v1/models"
    return f"{root}/models"


def _normalize_cursor_model_id(model_id: str) -> str:
    name = str(model_id or "").strip()
    if not name:
        return ""
    if name.lower() == "default":
        return DEFAULT_CURSOR_MODEL
    return name


def _cursor_models_from_items(items: list[Any]) -> list[CursorModelInfo]:
    models: list[CursorModelInfo] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, Mapping):
            raw_id = item.get("id") or ""
            display = str(item.get("displayName") or item.get("display_name") or "").strip()
        else:
            raw_id = getattr(item, "id", "") or ""
            display = str(getattr(item, "display_name", None) or getattr(item, "displayName", None) or "").strip()
        model_id = _normalize_cursor_model_id(str(raw_id))
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        models.append(CursorModelInfo(id=model_id, display_name=display or model_id))
    if DEFAULT_CURSOR_MODEL not in seen:
        models.insert(0, CursorModelInfo(id=DEFAULT_CURSOR_MODEL, display_name="Auto"))
    return models


async def _list_cursor_models_http(api_key: str, *, base_url: str = "") -> list[CursorModelInfo]:
    import httpx

    url = _cursor_models_url(base_url)
    headers = {"Accept": "application/json"}
    async with httpx.AsyncClient(timeout=12.0) as client:
        # Cloud Agents docs: Basic auth with API key as username and empty password.
        response = await client.get(url, auth=(api_key, ""), headers=headers)
        if response.status_code == 401:
            response = await client.get(
                url,
                headers={**headers, "Authorization": f"Bearer {api_key}"},
            )
        response.raise_for_status()
        payload = response.json()
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise RuntimeError("Cursor /v1/models response missing items[]")
    models = _cursor_models_from_items(items)
    if not models:
        raise RuntimeError("Cursor /v1/models returned no models")
    return models


async def _list_cursor_models_sdk(api_key: str) -> list[CursorModelInfo]:
    async with await AsyncClient.launch_bridge(workspace=_bridge_workspace()) as client:
        items = await client.list_models(api_key=api_key)
    return _cursor_models_from_items(list(items or []))


async def list_cursor_model_infos(api_key: str, *, base_url: str = "") -> list[CursorModelInfo]:
    """Live Cursor model catalog for agent selection (HTTP /v1/models, SDK bridge fallback)."""
    key = api_key.strip()
    if not key:
        return [CursorModelInfo(id=DEFAULT_CURSOR_MODEL, display_name="Auto")]

    try:
        return await _list_cursor_models_http(key, base_url=base_url)
    except Exception as http_exc:  # noqa: BLE001 — fall back to bridge ListModels
        try:
            models = await _list_cursor_models_sdk(key)
        except Exception as sdk_exc:  # noqa: BLE001
            raise RuntimeError(f"Cursor model list failed via HTTP ({http_exc}) and SDK ({sdk_exc})") from sdk_exc
        return models


async def list_cursor_models(api_key: str, *, base_url: str = "") -> list[str]:
    """List Cursor model ids available to this API key."""
    return [item.id for item in await list_cursor_model_infos(api_key, base_url=base_url)]


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


@cache
def _bridge_workspace() -> str:
    """Stable per-process workspace for the SDK bridge (cloud agents do not need a real repo checkout)."""
    return tempfile.mkdtemp(prefix="norns-cursor-bridge-")
