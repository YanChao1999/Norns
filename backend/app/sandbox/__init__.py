"""Pluggable agent sandbox runtimes for workspace isolation / AI governance.

Today
  directory — copy workspace under ~/.norns/sandboxes/; tools use the copy path
              (isolation by convention — does not block host ``rm -rf``).
  docker    — same copy + hardened container: only the copy is bind-mounted,
              ``--cap-drop ALL``, read-only rootfs, no-new-privileges; tmpfs for
              /tmp (falls back to directory if Docker is missing).
  none      — no copy; agents use the real checkout.

Allowlist the ``sandbox`` plugin so agents get MCP/function tools
(``sandbox_info``, ``sandbox_run``, …) to inspect the copy, run commands in the
jail (docker exec when available), and stage files for reproduce / env-build tasks.

Later
  microVM when containers are not enough; gVisor (or similar) plus a policy layer
  that controls what an agent runtime may exec, read, write, and reach on the network.
"""

from __future__ import annotations

from .base import SandboxHandle, SandboxProvider
from .runtime import (
    get_sandbox_provider,
    handle_from_context,
    handle_from_env,
    prepare_sandbox,
    resolve_under_root,
    run_in_sandbox,
    sandbox_env_vars,
    serialize_sandbox,
)

__all__ = [
    "SandboxHandle",
    "SandboxProvider",
    "get_sandbox_provider",
    "handle_from_context",
    "handle_from_env",
    "prepare_sandbox",
    "resolve_under_root",
    "run_in_sandbox",
    "sandbox_env_vars",
    "serialize_sandbox",
]
