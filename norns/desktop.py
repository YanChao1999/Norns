from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn


def _stage_checkout_ui() -> None:
    """Build norns/web from frontend/ when running from a git checkout."""
    try:
        from norns_build import stage_control_room
    except ImportError:
        return
    try:
        stage_control_room()
    except Exception as exc:
        print(f"Could not stage Control Room UI: {exc}", file=sys.stderr)


def run_ide(*, host: str, port: int, open_window: bool = True) -> int:
    _stage_checkout_ui()
    from backend.app.main import app

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    if not _wait_until_healthy(host, port):
        print(f"Norns server failed to start at http://{host}:{port}", file=sys.stderr)
        return 1
    if not _ui_is_reachable(host, port):
        print(
            "Control Room UI is not packaged. From a git checkout run: bash scripts/stage-ui.sh",
            file=sys.stderr,
        )
        if open_window:
            server.should_exit = True
            thread.join(timeout=5)
            return 1

    url = f"http://{host}:{port}"
    if not open_window:
        print(f"Norns local server listening on {url}")
        thread.join()
        return 0

    command = electron_command()
    if command is None:
        print(f"Opened Control Room at {url}")
        print(electron_install_help(), file=sys.stderr)
        webbrowser.open(url)
        thread.join()
        return 0

    env = os.environ.copy()
    env["NORNS_URL"] = url
    try:
        completed = subprocess.run(command, cwd=command[-1], env=env, check=False)
    except OSError as exc:
        print(electron_install_help(), file=sys.stderr)
        print(exc, file=sys.stderr)
        server.should_exit = True
        return 1
    server.should_exit = True
    thread.join(timeout=5)
    return 0 if completed.returncode == 0 else completed.returncode


def electron_app_dir() -> Path | None:
    override = os.environ.get("NORNS_ELECTRON_APP", "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        return path if (path / "main.js").is_file() else None
    packaged = Path(__file__).resolve().parent / "electron"
    if (packaged / "main.js").is_file():
        return packaged
    return None


def electron_command() -> list[str] | None:
    app_dir = electron_app_dir()
    if app_dir is None:
        return None
    binary = _electron_binary(app_dir)
    if binary is None:
        return None
    return [str(binary), str(app_dir)]


def electron_install_help() -> str:
    return (
        "Electron is optional. Norns already opened in your browser.\n"
        "For a desktop window, install Node.js then npm install in the packaged norns/electron directory.\n"
        "Or set NORNS_ELECTRON to an electron binary."
    )


def _electron_binary(app_dir: Path) -> Path | None:
    override = os.environ.get("NORNS_ELECTRON", "").strip()
    if override:
        path = Path(override).expanduser()
        return path if path.exists() else None
    if _electron_dist_ready(app_dir):
        bindir = app_dir / "node_modules" / ".bin"
        names = ("electron.cmd", "electron.exe", "electron") if os.name == "nt" else ("electron",)
        for name in names:
            candidate = bindir / name
            if candidate.exists():
                return candidate
    found = shutil.which("electron")
    return Path(found) if found else None


def _electron_dist_ready(app_dir: Path) -> bool:
    pkg = app_dir / "node_modules" / "electron"
    return (pkg / "path.txt").is_file() or (pkg / "dist").exists()


def _ui_is_reachable(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=0.4) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return False


def _wait_until_healthy(host: str, port: int, attempts: int = 50) -> bool:
    url = f"http://{host}:{port}/api/health"
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=0.4) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(0.1)
    return False
