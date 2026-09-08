"""Pluggable agent sandbox runtimes for workspace isolation / AI governance.

Today
  directory — copy workspace under ~/.norns/sandboxes/; tools use the copy path
              (isolation by convention — does not block host ``rm -rf``).
  docker    — same copy + hardened container: only the copy is bind-mounted,
              ``--cap-drop ALL``, read-only rootfs, no-new-privileges; tmpfs for
              /tmp (falls back to directory if Docker is missing).
  none      — no copy; agents use the real checkout.

Later
  microVM when containers are not enough; gVisor (or similar) plus a policy layer
  that controls what an agent runtime may exec, read, write, and reach on the network.
"""

from __future__ import annotations

from .base import SandboxHandle, SandboxProvider
from .runtime import get_sandbox_provider, prepare_sandbox, run_in_sandbox, serialize_sandbox

__all__ = [
    "SandboxHandle",
    "SandboxProvider",
    "get_sandbox_provider",
    "prepare_sandbox",
    "run_in_sandbox",
    "serialize_sandbox",
]
