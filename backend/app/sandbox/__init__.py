"""Pluggable agent sandbox runtimes for workspace isolation / AI governance.

Today (isolation by convention)
  directory — copy workspace under ~/.norns/sandboxes/; tools use the copy path.
  docker    — same copy + long-lived container bind-mount (falls back to directory).
  none      — no copy; agents use the real checkout.

Not enforced yet: a careless ``rm -rf`` on absolute host paths can still damage the machine.

Next (OS / container policy — block host rm -rf)
  Hardened Docker: no host mounts except the sandbox copy, dropped capabilities,
  read-only rootfs, optional network policy.
  Then microVM for stronger isolation when containers are not enough.

Later
  gVisor (or similar user-space kernel) plus a policy layer that controls what an
  agent runtime may exec, read, write, and reach on the network.
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
