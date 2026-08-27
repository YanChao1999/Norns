"""Stdio MCP entry: python -m norns.mcp --plugins norns,github,jira."""

from __future__ import annotations

import argparse
import asyncio

from backend.app.plugins.mcp_protocol import serve_stdio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="norns mcp", description="Run Norns tools as an MCP server on stdin/stdout.")
    parser.add_argument(
        "--plugins",
        default="",
        help="Comma-separated plugin ids (norns,github,jira,polarion). Empty = all built-ins.",
    )
    args = parser.parse_args(argv)
    names = [part.strip() for part in str(args.plugins).split(",") if part.strip()]
    asyncio.run(serve_stdio(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
