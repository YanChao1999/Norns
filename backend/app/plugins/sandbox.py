"""Sandbox MCP / function tools for reproduce and environment-build tasks."""

from __future__ import annotations

import asyncio
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..sandbox import (
    SandboxHandle,
    handle_from_context,
    resolve_under_root,
    run_in_sandbox,
)
from .base import Plugin, PluginContext, ToolSpec

OBJECT = {"type": "object", "properties": {}}


def _bind(execute, context: PluginContext, *, with_context: bool = True):
    async def bound(arguments: dict[str, Any]) -> Any:
        if with_context:
            return await execute(dict(arguments), context)
        return await execute(dict(arguments))

    return bound


class SandboxPlugin(Plugin):
    name = "sandbox"
    title = "Sandbox"
    description = (
        "Inspect and operate the per-run workspace sandbox: run commands in the jail "
        "(docker exec when hardened Docker is active), list/read/write files under the "
        "copy, and pull paths from the source checkout — useful for reproduce and env-build tasks."
    )
    builtin = True
    requires_connector = None

    def tools(self, context: PluginContext) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="sandbox_info",
                description=(
                    "Describe the sandbox for this agent run: backend (directory/docker/none), "
                    "copy path, source checkout, container id, and hardening policy when present."
                ),
                input_schema={**OBJECT},
                execute=_bind(_sandbox_info, context),
            ),
            ToolSpec(
                name="sandbox_list",
                description="List files and directories under a path inside the sandbox copy (default: root).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path under the sandbox root (default '.').",
                        },
                    },
                },
                execute=_bind(_sandbox_list, context),
            ),
            ToolSpec(
                name="sandbox_read_file",
                description="Read a UTF-8 text file inside the sandbox copy (path relative to sandbox root).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "max_bytes": {"type": "integer", "description": "Cap returned size (default 200000)."},
                    },
                    "required": ["path"],
                },
                execute=_bind(_sandbox_read_file, context),
            ),
            ToolSpec(
                name="sandbox_write_file",
                description=(
                    "Write a UTF-8 text file inside the sandbox copy (path relative to sandbox root). "
                    "Use this to drop repro scripts or env config without touching the source checkout."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "mkdirs": {"type": "boolean", "description": "Create parent dirs (default true)."},
                    },
                    "required": ["path", "content"],
                },
                execute=_bind(_sandbox_write_file, context),
            ),
            ToolSpec(
                name="sandbox_copy_in",
                description=(
                    "Copy a file or directory from the source checkout into the sandbox copy. "
                    "Paths are relative to source_path and sandbox root respectively."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Relative path under the source checkout."},
                        "dest": {
                            "type": "string",
                            "description": "Relative path under the sandbox (default: same as source).",
                        },
                    },
                    "required": ["source"],
                },
                execute=_bind(_sandbox_copy_in, context),
            ),
            ToolSpec(
                name="sandbox_run",
                description=(
                    "Run a command inside the sandbox jail. With backend=docker and a live container, "
                    "this uses docker exec (hardened). Otherwise it runs with cwd set to the sandbox copy. "
                    "Use for install/build/repro steps (e.g. pytest, npm test, ./scripts/repro.sh)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {
                            "description": "Argv as a string array, or a shell string (split with shlex).",
                            "oneOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}, "minItems": 1},
                            ],
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Seconds before the command is killed (default 600).",
                        },
                    },
                    "required": ["command"],
                },
                execute=_bind(_sandbox_run, context),
            ),
        ]


def _require_handle(context: PluginContext | None) -> SandboxHandle | dict[str, str]:
    handle = handle_from_context(context)
    if handle is None:
        return {
            "error": (
                "No sandbox for this run. Set [sandbox] backend to directory or docker in config.toml, "
                "give the board/agent a local workspace path, then rerun. Allowlist the sandbox plugin "
                "under Agent → Tools."
            )
        }
    return handle


async def _sandbox_info(arguments: dict[str, Any], context: PluginContext | None = None) -> Any:
    del arguments
    handle = handle_from_context(context)
    if handle is None:
        return {
            "active": False,
            "backend": "none",
            "path": None,
            "hint": "No sandbox prepared for this run (backend=none, missing workspace, or prepare skipped).",
        }
    meta = dict(handle.metadata or {})
    return {
        "active": True,
        "backend": handle.backend,
        "path": handle.path,
        "source_path": handle.source_path or None,
        "container_id": meta.get("container_id"),
        "workdir": meta.get("workdir"),
        "hardened": meta.get("hardened"),
        "policy": meta.get("policy"),
        "image": meta.get("image"),
    }


async def _sandbox_list(arguments: dict[str, Any], context: PluginContext | None = None) -> Any:
    handle = _require_handle(context)
    if isinstance(handle, dict):
        return handle
    try:
        target = resolve_under_root(handle.path, str(arguments.get("path") or "."))
    except ValueError as exc:
        return {"error": str(exc)}
    if not target.exists():
        return {"error": f"Path not found: {arguments.get('path') or '.'}"}
    if not target.is_dir():
        return {"error": f"Not a directory: {arguments.get('path') or '.'}"}
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        entries.append(
            {
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
                "path": str(child.relative_to(Path(handle.path).resolve())),
            }
        )
    return {"path": str(target.relative_to(Path(handle.path).resolve())) or ".", "entries": entries}


async def _sandbox_read_file(arguments: dict[str, Any], context: PluginContext | None = None) -> Any:
    handle = _require_handle(context)
    if isinstance(handle, dict):
        return handle
    rel = str(arguments.get("path") or "").strip()
    if not rel:
        return {"error": "path is required"}
    try:
        target = resolve_under_root(handle.path, rel)
    except ValueError as exc:
        return {"error": str(exc)}
    if not target.is_file():
        return {"error": f"Not a file: {rel}"}
    max_bytes = int(arguments.get("max_bytes") or 200_000)
    max_bytes = max(1, min(max_bytes, 2_000_000))
    data = target.read_bytes()
    truncated = len(data) > max_bytes
    text = data[:max_bytes].decode("utf-8", errors="replace")
    return {"path": rel, "content": text, "truncated": truncated, "bytes": len(data)}


async def _sandbox_write_file(arguments: dict[str, Any], context: PluginContext | None = None) -> Any:
    handle = _require_handle(context)
    if isinstance(handle, dict):
        return handle
    rel = str(arguments.get("path") or "").strip()
    if not rel:
        return {"error": "path is required"}
    try:
        target = resolve_under_root(handle.path, rel)
    except ValueError as exc:
        return {"error": str(exc)}
    mkdirs = arguments.get("mkdirs", True)
    if mkdirs is not False:
        target.parent.mkdir(parents=True, exist_ok=True)
    content = str(arguments.get("content") if arguments.get("content") is not None else "")
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": rel, "bytes": len(content.encode("utf-8"))}


async def _sandbox_copy_in(arguments: dict[str, Any], context: PluginContext | None = None) -> Any:
    handle = _require_handle(context)
    if isinstance(handle, dict):
        return handle
    source_root = str(handle.source_path or "").strip()
    if not source_root:
        return {"error": "Sandbox has no source_path; cannot copy from the original checkout."}
    src_rel = str(arguments.get("source") or "").strip()
    if not src_rel:
        return {"error": "source is required"}
    dest_rel = str(arguments.get("dest") or src_rel).strip() or src_rel
    try:
        src = resolve_under_root(source_root, src_rel)
        dest = resolve_under_root(handle.path, dest_rel)
    except ValueError as exc:
        return {"error": str(exc)}
    if not src.exists():
        return {"error": f"Source not found: {src_rel}"}
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest, symlinks=False)
    else:
        shutil.copy2(src, dest)
    return {"ok": True, "source": src_rel, "dest": dest_rel}


async def _sandbox_run(arguments: dict[str, Any], context: PluginContext | None = None) -> Any:
    handle = _require_handle(context)
    if isinstance(handle, dict):
        return handle
    raw = arguments.get("command")
    try:
        argv = _normalize_command(raw)
    except ValueError as exc:
        return {"error": str(exc)}
    timeout = float(arguments.get("timeout") or 600.0)
    timeout = max(1.0, min(timeout, 3600.0))

    def _run():
        return run_in_sandbox(handle, argv, timeout=timeout)

    try:
        completed = await asyncio.to_thread(_run)
    except FileNotFoundError as exc:
        return {"error": f"Command not found: {exc}"}
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s", "command": argv}
    except Exception as exc:  # noqa: BLE001 — surface to the agent
        return {"error": str(exc), "command": argv}

    stdout = (completed.stdout or "")[-50_000:]
    stderr = (completed.stderr or "")[-50_000:]
    return {
        "returncode": completed.returncode,
        "command": argv,
        "backend": handle.backend,
        "cwd": handle.path,
        "stdout": stdout,
        "stderr": stderr,
    }


def _normalize_command(raw: Any) -> list[str]:
    if isinstance(raw, list):
        parts = [str(part) for part in raw if str(part).strip()]
        if not parts:
            raise ValueError("command array must not be empty")
        return parts
    text = str(raw or "").strip()
    if not text:
        raise ValueError("command is required")
    parts = shlex.split(text)
    if not parts:
        raise ValueError("command is required")
    return parts
