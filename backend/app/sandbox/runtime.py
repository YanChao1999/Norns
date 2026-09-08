from __future__ import annotations

from pathlib import Path
from typing import Any

from ..workspace import Workspace
from .base import SandboxHandle, SandboxProvider
from .providers import (
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
    "prepare_sandbox",
    "run_in_sandbox",
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
