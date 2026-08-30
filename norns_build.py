"""Build helpers so `pip install` / `uv tool install` ship the Control Room UI."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

# Same image docker compose uses for `npm run dev` on the frontend service.
COMPOSE_NODE_IMAGE = "public.ecr.aws/docker/library/node:20"


def project_root() -> Path:
    return Path(__file__).resolve().parent


def stage_control_room(root: Path | None = None, *, force: bool = False) -> Path:
    """Copy a complete Vite build into norns/web.

    With force=False (norns run / wheel build), skip when norns/web is already complete.
    scripts/stage-ui.sh passes force=True so frontend source changes are rebuilt.
    """
    root = root or project_root()
    dest = root / "norns" / "web"
    frontend = root / "frontend"
    dist = frontend / "dist"
    if not force:
        if _web_ui_is_complete(dest):
            return dest
        if _web_ui_is_complete(dist):
            _replace_tree(dist, dest)
            return dest
    if not (frontend / "package.json").is_file():
        raise RuntimeError(
            "Control Room UI is missing from this source tree. Install a prebuilt Norns wheel, "
            "or build from a git checkout that includes frontend/ with Node.js 20+ and npm."
        )
    built = _build_frontend(frontend)
    _replace_tree(built, dest)
    return dest


def _web_ui_is_complete(root: Path) -> bool:
    """Match backend.app.ui_assets.ui_is_complete — index.html plus a stylesheet."""
    index = root / "index.html"
    if not index.is_file():
        return False
    html = index.read_text(encoding="utf-8", errors="ignore")
    if 'rel="stylesheet"' in html or ".css" in html:
        return True
    assets = root / "assets"
    return assets.is_dir() and any(assets.glob("*.css"))


def _replace_tree(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def _can_build_in_place(frontend: Path) -> bool:
    if not os.access(frontend, os.W_OK):
        return False
    for name in ("node_modules", "dist"):
        path = frontend / name
        if path.exists() and not os.access(path, os.W_OK):
            return False
    return True


def _ui_build_cache() -> Path:
    override = os.environ.get("NORNS_UI_BUILD_DIR", "").strip()
    if override:
        return Path(override)
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "norns" / "ui-build"


def _prepare_cache_worktree(frontend: Path) -> Path:
    """Copy frontend sources to a writable cache when docker compose owns node_modules/dist."""
    work = _ui_build_cache()
    work.mkdir(parents=True, exist_ok=True)
    for item in frontend.iterdir():
        if item.name in {"node_modules", "dist"}:
            continue
        dest = work / item.name
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        elif dest.is_dir():
            shutil.rmtree(dest)
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    return work


def _build_frontend(frontend: Path) -> Path:
    work = frontend if _can_build_in_place(frontend) else _prepare_cache_worktree(frontend)
    npm = _npm_executable()
    if npm is not None:
        _run_npm(npm, work)
    else:
        _build_frontend_with_docker(work)
    dist = work / "dist"
    if not _web_ui_is_complete(dist):
        raise RuntimeError(
            "frontend build did not produce a Control Room stylesheet "
            "(index.html without CSS is the unstyled login docker compose does not show)"
        )
    return dist


def _node_bindir(npm: str) -> Path:
    """Directory that contains `node` for this npm. Do not resolve() the npm symlink.

    Official Node tarballs link bin/npm -> lib/node_modules/npm/bin/npm-cli.js, so
    resolve().parent is not the directory that has the node binary.
    """
    path = Path(npm).expanduser()
    node_name = "node.exe" if os.name == "nt" else "node"
    if (path.parent / node_name).is_file():
        return path.parent
    resolved = path.resolve().parent
    if (resolved / node_name).is_file():
        return resolved
    return path.parent


def _npm_env(npm: str) -> dict[str, str]:
    """Keep node on PATH for npm and for scripts it spawns (`tsc`, `vite`)."""
    env = os.environ.copy()
    env["PATH"] = str(_node_bindir(npm)) + os.pathsep + env.get("PATH", "")
    return env


def _npm_argv(npm: str, *args: str) -> list[str]:
    """Run npm via its sibling node binary so we never depend on `/usr/bin/env node`."""
    bindir = _node_bindir(npm)
    node_name = "node.exe" if os.name == "nt" else "node"
    node = bindir / node_name
    script = Path(npm).expanduser().resolve()
    if node.is_file():
        return [str(node), str(script), *args]
    return [str(Path(npm).expanduser()), *args]


def _run_npm(npm: str, work: Path) -> None:
    env = _npm_env(npm)
    subprocess.run(_npm_argv(npm, "ci"), cwd=work, check=True, env=env)
    subprocess.run(_npm_argv(npm, "run", "build"), cwd=work, check=True, env=env)


def _npm_executable() -> str | None:
    names = ("npm.cmd", "npm.exe", "npm") if os.name == "nt" else ("npm",)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    portable_name = "npm.cmd" if os.name == "nt" else "npm"
    portable = project_root() / ".tools" / "node" / "bin" / portable_name
    node_name = "node.exe" if os.name == "nt" else "node"
    if portable.is_file() and (portable.parent / node_name).is_file():
        return str(portable)
    return None


def _docker_executable() -> str | None:
    names = ("docker.exe", "docker") if os.name == "nt" else ("docker",)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _node_image() -> str:
    override = os.environ.get("NORNS_NODE_IMAGE", "").strip()
    return override or COMPOSE_NODE_IMAGE


def docker_build_command(work: Path) -> list[str]:
    docker = _docker_executable()
    if docker is None:
        raise RuntimeError(
            "npm was not found on PATH and docker is not available. "
            "Install Node.js 20+, or Docker so norns run can use the same node:20 image as docker compose up. "
            "A published norns-ide wheel already includes the UI and does not need Node."
        )
    command = [docker, "run", "--rm", "-e", "HOME=/tmp", "-e", "npm_config_cache=/tmp/npm-cache"]
    if hasattr(os, "getuid"):
        command.extend(["-u", f"{os.getuid()}:{os.getgid()}"])
    command.extend(
        [
            "-v",
            f"{work.resolve()}:/app",
            "-w",
            "/app",
            _node_image(),
            "sh",
            "-c",
            "npm ci && npm run build",
        ]
    )
    return command


def _build_frontend_with_docker(work: Path) -> None:
    subprocess.run(docker_build_command(work), check=True)


try:
    from setuptools.command.build_py import build_py
    from setuptools.command.sdist import sdist
except ImportError:  # pragma: no cover - unit tests may omit setuptools
    build_py = object  # type: ignore[misc,assignment]
    sdist = object  # type: ignore[misc,assignment]


class BuildPy(build_py):  # type: ignore[misc,valid-type]
    def run(self) -> None:
        stage_control_room()
        super().run()


class Sdist(sdist):  # type: ignore[misc,valid-type]
    def run(self) -> None:
        stage_control_room()
        super().run()
