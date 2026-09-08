from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from ..workspace import Workspace
from .base import SandboxHandle

logger = logging.getLogger("norns")

# Heavy / regenerable trees — keep the copy lean without mutating the source.
COPY_IGNORE = shutil.ignore_patterns(
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
    "*.pyc",
    ".DS_Store",
)

DEFAULT_DOCKER_IMAGE = "public.ecr.aws/docker/library/python:3.12-slim"
CONTAINER_WORKDIR = "/workspace"


def default_sandbox_root() -> Path:
    override = os.environ.get("NORNS_SANDBOX_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    home = os.environ.get("NORNS_HOME", "").strip()
    base = Path(home).expanduser() if home else Path.home() / ".norns"
    return (base / "sandboxes").resolve()


def docker_executable() -> str | None:
    names = ("docker.exe", "docker") if os.name == "nt" else ("docker",)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


class DirectoryCopySandboxProvider:
    """Copy the local workspace into ~/.norns/sandboxes/... for the run."""

    name = "directory"

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or default_sandbox_root()

    def prepare(
        self,
        *,
        run_id: str,
        card_id: str,
        board_id: str,
        source: Workspace,
    ) -> SandboxHandle | None:
        source_path = str(getattr(source, "path", "") or "").strip()
        if not source_path:
            return None
        src = Path(source_path).expanduser()
        if not src.is_dir():
            return None
        dest = self.root / _safe_segment(board_id) / _safe_segment(card_id) / _safe_segment(run_id)
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest, ignore=COPY_IGNORE, symlinks=False, dirs_exist_ok=False)
        return SandboxHandle(
            path=str(dest),
            backend=self.name,
            source_path=str(src.resolve()),
            metadata={"root": str(self.root)},
        )

    def cleanup(self, handle: SandboxHandle) -> None:
        path = str(handle.path or "").strip()
        if not path:
            return
        target = Path(path)
        try:
            root = self.root.resolve()
            resolved = target.resolve()
            if root not in resolved.parents and resolved != root:
                logger.warning("Refusing to clean sandbox outside root: %s", path)
                return
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
        except OSError as exc:
            logger.warning("Sandbox cleanup failed for %s: %s", path, exc)


class DockerSandboxProvider:
    """Directory copy plus a hardened long-lived Docker container.

    The agent workspace path on the host is the bind-mounted copy (so Cursor/file
    tools can edit it). Container isolation applies to commands run via
    ``run_in_sandbox`` / ``sandbox_run`` (``docker exec``). Falls back to
    directory-only when Docker is missing or ``docker run`` fails.

    Container policy: only the sandbox copy is bind-mounted (rw at /workspace),
    all Linux capabilities are dropped, rootfs is read-only, and no-new-privileges
    is set. Writable scratch uses tmpfs (/tmp, /var/tmp, /run) — not host paths.
    Absolute host paths outside the mount are not available inside the container.
    """

    name = "docker"

    def __init__(
        self,
        root: Path | None = None,
        *,
        image: str | None = None,
        docker_bin: str | None = None,
    ) -> None:
        self.copies = DirectoryCopySandboxProvider(root=root)
        self.image = (image or os.environ.get("NORNS_SANDBOX_IMAGE") or DEFAULT_DOCKER_IMAGE).strip()
        self._docker_bin = docker_bin

    def prepare(
        self,
        *,
        run_id: str,
        card_id: str,
        board_id: str,
        source: Workspace,
    ) -> SandboxHandle | None:
        handle = self.copies.prepare(run_id=run_id, card_id=card_id, board_id=board_id, source=source)
        if handle is None:
            return None
        docker = self._docker()
        if not docker:
            logger.warning("sandbox.backend=docker but Docker is not on PATH; using directory copy only")
            return _directory_fallback(handle, reason="docker_unavailable")
        container_name = f"norns-sb-{_safe_segment(run_id)}"
        try:
            container_id = _docker_run(
                docker,
                image=self.image,
                host_path=handle.path,
                container_name=container_name,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            logger.warning("docker run failed for sandbox; using directory copy only: %s", exc)
            return _directory_fallback(handle, reason="docker_run_failed")
        return SandboxHandle(
            path=handle.path,
            backend=self.name,
            source_path=handle.source_path,
            metadata={
                "root": str(self.copies.root),
                "container_id": container_id,
                "container_name": container_name,
                "image": self.image,
                "workdir": CONTAINER_WORKDIR,
                "hardened": True,
                "policy": list(DOCKER_HARDENING_POLICY),
            },
        )

    def cleanup(self, handle: SandboxHandle) -> None:
        meta = dict(handle.metadata or {})
        container_id = str(meta.get("container_id") or "").strip()
        docker = self._docker()
        if container_id and docker:
            try:
                subprocess.run(
                    [docker, "rm", "-f", container_id],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                logger.warning("Docker sandbox cleanup failed for %s: %s", container_id, exc)
        self.copies.cleanup(handle)

    def _docker(self) -> str | None:
        if self._docker_bin:
            return self._docker_bin
        return docker_executable()


def run_in_sandbox(
    handle: SandboxHandle, command: list[str], *, timeout: float = 600.0
) -> subprocess.CompletedProcess[str]:
    """Run a command inside the sandbox container when present, else on the host path."""
    meta = dict(handle.metadata or {})
    container_id = str(meta.get("container_id") or "").strip()
    workdir = str(meta.get("workdir") or CONTAINER_WORKDIR)
    if handle.backend == "docker" and container_id:
        docker = docker_executable()
        if not docker:
            raise RuntimeError("Docker sandbox has a container id but docker is not on PATH")
        return subprocess.run(
            [docker, "exec", "-w", workdir, container_id, *command],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    cwd = str(handle.path or "").strip() or None
    return subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True, timeout=timeout)


class NoneSandboxProvider:
    """No isolation — agents use the resolved workspace path directly."""

    name = "none"

    def prepare(
        self,
        *,
        run_id: str,
        card_id: str,
        board_id: str,
        source: Workspace,
    ) -> SandboxHandle | None:
        del run_id, card_id, board_id, source
        return None

    def cleanup(self, handle: SandboxHandle) -> None:
        del handle


class MicroVmSandboxProvider:
    """Reserved backend for stronger AI governance (Firecracker / microVM).

    Prefer hardened ``docker`` (copy-only mount, dropped caps, read-only rootfs)
    until containers are not enough. This backend is not implemented yet.
    """

    name = "microvm"

    def prepare(
        self,
        *,
        run_id: str,
        card_id: str,
        board_id: str,
        source: Workspace,
    ) -> SandboxHandle | None:
        del run_id, card_id, board_id, source
        logger.warning("sandbox.backend=microvm is not implemented yet; use backend=docker or directory until then")
        return None

    def cleanup(self, handle: SandboxHandle) -> None:
        del handle


class GvisorSandboxProvider:
    """Reserved backend for gVisor (or similar) plus an agent runtime policy layer.

    Intended to control what agents may exec, read, write, and reach on the network,
    beyond ordinary Docker. Not implemented yet.
    """

    name = "gvisor"

    def prepare(
        self,
        *,
        run_id: str,
        card_id: str,
        board_id: str,
        source: Workspace,
    ) -> SandboxHandle | None:
        del run_id, card_id, board_id, source
        logger.warning("sandbox.backend=gvisor is not implemented yet; use backend=docker or directory until then")
        return None

    def cleanup(self, handle: SandboxHandle) -> None:
        del handle


def _directory_fallback(handle: SandboxHandle, *, reason: str) -> SandboxHandle:
    meta = dict(handle.metadata or {})
    meta["fallback_from"] = "docker"
    meta["fallback_reason"] = reason
    return SandboxHandle(
        path=handle.path,
        backend="directory",
        source_path=handle.source_path,
        metadata=meta,
    )


# Flags recorded on the sandbox handle for observability / UI.
DOCKER_HARDENING_POLICY = (
    "bind-workspace-only",
    "cap-drop-all",
    "read-only-rootfs",
    "no-new-privileges",
)


def docker_run_command(
    docker: str,
    *,
    image: str,
    host_path: str,
    container_name: str,
) -> list[str]:
    """Build a hardened ``docker run`` argv for one sandbox container.

    Only the sandbox copy is mounted from the host. Rootfs is read-only; caps are
    dropped; writable areas are tmpfs, not additional host binds.
    """
    resolved = str(Path(host_path).resolve())
    return [
        docker,
        "run",
        "-d",
        "--name",
        container_name,
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        # Single host bind: the sandbox copy only (rw so agents can edit files).
        "--mount",
        f"type=bind,source={resolved},target={CONTAINER_WORKDIR}",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m",
        "--tmpfs",
        "/var/tmp:rw,nosuid,nodev,size=64m",
        "--tmpfs",
        "/run:rw,nosuid,nodev,size=64m",
        "-w",
        CONTAINER_WORKDIR,
        image,
        "sleep",
        "infinity",
    ]


def _docker_run(docker: str, *, image: str, host_path: str, container_name: str) -> str:
    command = docker_run_command(
        docker,
        image=image,
        host_path=host_path,
        container_name=container_name,
    )
    completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
    container_id = (completed.stdout or "").strip()
    if not container_id:
        raise RuntimeError("docker run returned an empty container id")
    return container_id


def _safe_segment(value: str) -> str:
    text = str(value or "unknown").strip() or "unknown"
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in text)[:80]
