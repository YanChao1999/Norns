"""Build helpers so `pip install` / `uv tool install` ship the Control Room UI."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent


def stage_control_room(root: Path | None = None) -> Path:
    """Copy frontend/dist into norns/web. No-op when the UI is already packaged."""
    root = root or project_root()
    dest = root / "norns" / "web"
    if (dest / "index.html").is_file():
        return dest
    frontend = root / "frontend"
    if not (frontend / "package.json").is_file():
        raise RuntimeError(
            "Control Room UI is missing from this source tree. Install a prebuilt Norns wheel, "
            "or build from a git checkout that includes frontend/ with Node.js 20+ and npm."
        )
    npm = _npm_executable()
    subprocess.run([npm, "ci"], cwd=frontend, check=True)
    subprocess.run([npm, "run", "build"], cwd=frontend, check=True)
    dist = frontend / "dist"
    if not (dist / "index.html").is_file():
        raise RuntimeError("frontend build did not produce dist/index.html")
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(dist, dest)
    return dest


def _npm_executable() -> str:
    names = ("npm.cmd", "npm.exe", "npm") if os.name == "nt" else ("npm",)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("Node.js 20+ and npm are required to build Norns from source (npm was not found on PATH).")


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
