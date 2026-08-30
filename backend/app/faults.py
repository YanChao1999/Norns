"""Local fault injection for runner / tool-loop / MCP tests.

Set NORNS_INJECT to a comma-separated list (off by default):

- runner_timeout — raise TimeoutError before the model runs
- loop_tool_error — first OpenAI tool call returns an injected error instead of executing
- mcp_error — MCP tools/call returns an injected error
"""

from __future__ import annotations

import os
from typing import Any

ENV = "NORNS_INJECT"
RUNNER_TIMEOUT = "runner_timeout"
LOOP_TOOL_ERROR = "loop_tool_error"
MCP_ERROR = "mcp_error"


def injected(*names: str) -> bool:
    wanted = {part.strip().lower() for part in str(os.environ.get(ENV) or "").split(",") if part.strip()}
    return any(name.lower() in wanted for name in names)


def runner_timeout_if_injected() -> None:
    if injected(RUNNER_TIMEOUT):
        raise TimeoutError()


def loop_tool_error_if_injected(name: str) -> dict[str, Any] | None:
    if injected(LOOP_TOOL_ERROR):
        return {"error": f"injected: {ENV}={LOOP_TOOL_ERROR}", "tool": name}
    return None


def mcp_error_if_injected(name: str) -> dict[str, Any] | None:
    if injected(MCP_ERROR):
        return {"error": f"injected: {ENV}={MCP_ERROR}", "tool": name}
    return None
