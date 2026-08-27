"""Minimal MCP JSON-RPC stdio server (tools/list + tools/call)."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, TextIO

from .base import PluginContext, ToolSpec
from .catalog import dump_mcp_tool_result, load_plugin_catalog_from_db


async def serve_stdio(
    plugin_names: list[str],
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    catalog = await load_plugin_catalog_from_db()
    allowlist = plugin_names or [plugin.name for plugin in catalog.plugins if plugin.builtin]
    tools = catalog.tools(allowlist, PluginContext())
    tool_map = {tool.name: tool for tool in tools}
    reader = stdin or sys.stdin
    writer = stdout or sys.stdout
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, reader.readline)
        if line == "":
            break
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = await _handle(message, tools, tool_map)
        if response is None:
            continue
        writer.write(json.dumps(response) + "\n")
        writer.flush()


async def _handle(
    message: dict[str, Any], tools: list[ToolSpec], tool_map: dict[str, ToolSpec]
) -> dict[str, Any] | None:
    method = str(message.get("method") or "")
    request_id = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if method.startswith("notifications/") or request_id is None:
        return None
    if method == "initialize":
        return _ok(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "norns", "version": "0.0.1"},
            },
        )
    if method in {"ping", "tools/list"}:
        if method == "ping":
            return _ok(request_id, {})
        return _ok(request_id, {"tools": [tool.mcp_tool() for tool in tools]})
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        tool = tool_map.get(name)
        if tool is None:
            return _ok(
                request_id,
                {
                    "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                    "isError": True,
                },
            )
        try:
            result = await tool.execute(arguments)
            text = dump_mcp_tool_result(result)
            is_error = isinstance(result, dict) and "error" in result
            return _ok(request_id, {"content": [{"type": "text", "text": text}], "isError": is_error})
        except Exception as exc:  # pragma: no cover - exercised via protocol tests with mocks
            return _ok(
                request_id,
                {"content": [{"type": "text", "text": str(exc)}], "isError": True},
            )
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def _ok(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
