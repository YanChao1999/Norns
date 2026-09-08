from __future__ import annotations

from pathlib import Path
from typing import Any

from ..workspace import Workspace
from .base import SandboxHandle, SandboxProvider
from .providers import (
    CONTAINER_WORKDIR,
    DEFAULT_DOCKER_IMAGE,
    DirectoryCopySandboxProvider,
    DockerSandboxProvider,
    GvisorSandboxProvider,
    MicroVmSandboxProvider,
    NoneSandboxProvider,
    run_in_sandbox,
)

__all__ = [
    "get_sandbox_provider",
    "handle_from_context",
    "handle_from_env",
    "prepare_sandbox",
    "resolve_under_root",
    "run_in_sandbox",
    "sandbox_env_vars",
    "serialize_sandbox",
]


def get_sandbox_provider(settings: Any | None = None, *, root: Any | None = None) -> SandboxProvider:
    backend = "directory"
    if settings is not None:
        backend = str(getattr(settings, "sandbox_backend", "") or "directory").strip().lower() or "directory"
    if backend == "none":
        return NoneSandboxProvider()
    if backend == "microvm":
        return MicroVmSandboxProvider()
    if backend == "gvisor":
        return GvisorSandboxProvider()

    resolved_root = root
    if resolved_root is None and settings is not None:
        configured = str(getattr(settings, "sandbox_root", "") or "").strip()
        if configured:
            resolved_root = Path(configured).expanduser()

    if backend == "docker":
        image = DEFAULT_DOCKER_IMAGE
        if settings is not None:
            configured_image = str(getattr(settings, "sandbox_image", "") or "").strip()
            if configured_image:
                image = configured_image
        return DockerSandboxProvider(root=resolved_root, image=image)

    if resolved_root is not None:
        return DirectoryCopySandboxProvider(root=resolved_root)
    return DirectoryCopySandboxProvider()


def prepare_sandbox(
    settings: Any | None,
    *,
    run_id: str,
    card_id: str,
    board_id: str,
    source: Workspace,
) -> tuple[SandboxProvider, SandboxHandle | None]:
    provider = get_sandbox_provider(settings)
    handle = provider.prepare(run_id=run_id, card_id=card_id, board_id=board_id, source=source)
    return provider, handle


def serialize_sandbox(handle: SandboxHandle | None, *, source: Workspace | None = None) -> dict[str, object]:
    if handle is None:
        return {
            "backend": "none",
            "path": None,
            "source_path": getattr(source, "path", None) if source else None,
        }
    return {
        "backend": handle.backend,
        "path": handle.path,
        "source_path": handle.source_path or (getattr(source, "path", None) if source else None),
        "metadata": dict(handle.metadata or {}),
    }


def sandbox_env_vars(handle: SandboxHandle | None) -> dict[str, str]:
    """Env passed into the Norns MCP child so sandbox tools can reconstruct the handle."""
    if handle is None:
        return {}
    meta = dict(handle.metadata or {})
    env = {
        "NORNS_SANDBOX_PATH": str(handle.path or "").strip(),
        "NORNS_SANDBOX_BACKEND": str(handle.backend or "").strip(),
        "NORNS_SANDBOX_SOURCE": str(handle.source_path or "").strip(),
        "NORNS_SANDBOX_CONTAINER_ID": str(meta.get("container_id") or "").strip(),
        "NORNS_SANDBOX_WORKDIR": str(meta.get("workdir") or CONTAINER_WORKDIR).strip(),
    }
    return {key: value for key, value in env.items() if value}


def handle_from_env(environ: dict[str, str] | None = None) -> SandboxHandle | None:
    """Rebuild a SandboxHandle from NORNS_SANDBOX_* env (MCP subprocess)."""
    import os

    env = environ if environ is not None else os.environ
    path = str(env.get("NORNS_SANDBOX_PATH") or "").strip()
    if not path:
        return None
    backend = str(env.get("NORNS_SANDBOX_BACKEND") or "directory").strip() or "directory"
    source_path = str(env.get("NORNS_SANDBOX_SOURCE") or "").strip()
    container_id = str(env.get("NORNS_SANDBOX_CONTAINER_ID") or "").strip()
    workdir = str(env.get("NORNS_SANDBOX_WORKDIR") or CONTAINER_WORKDIR).strip() or CONTAINER_WORKDIR
    metadata: dict[str, object] = {"workdir": workdir}
    if container_id:
        metadata["container_id"] = container_id
    return SandboxHandle(path=path, backend=backend, source_path=source_path, metadata=metadata)


def handle_from_context(context: Any | None) -> SandboxHandle | None:
    """Rebuild a SandboxHandle from PluginContext fields, falling back to env."""
    if context is not None:
        path = str(getattr(context, "sandbox_path", "") or "").strip()
        if path:
            backend = str(getattr(context, "sandbox_backend", "") or "directory").strip() or "directory"
            source_path = str(getattr(context, "sandbox_source_path", "") or "").strip()
            container_id = str(getattr(context, "sandbox_container_id", "") or "").strip()
            workdir = str(getattr(context, "sandbox_workdir", "") or "").strip() or CONTAINER_WORKDIR
            metadata: dict[str, object] = {"workdir": workdir}
            if container_id:
                metadata["container_id"] = container_id
            return SandboxHandle(path=path, backend=backend, source_path=source_path, metadata=metadata)
        # Workspace may already be the sandbox copy path for this run.
        workspace = str(getattr(context, "workspace_path", "") or "").strip()
        if workspace:
            env_handle = handle_from_env()
            if env_handle is not None:
                return env_handle
    return handle_from_env()


def resolve_under_root(root: str | Path, relative: str) -> Path:
    """Resolve ``relative`` under ``root``; raise ValueError on escape."""
    base = Path(root).expanduser().resolve()
    text = str(relative or "").strip()
    if not text or text == ".":
        return base
    candidate = (base / text).resolve()
    if candidate != base and base not in candidate.parents:
        raise ValueError(f"Path escapes sandbox root: {relative}")
    return candidate
