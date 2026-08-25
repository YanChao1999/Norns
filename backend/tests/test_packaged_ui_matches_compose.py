"""Assert pip/uv packaged UI is the same Control Room docker compose serves from Vite."""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from backend.app.ui_assets import (
    COMPOSE_CSS_MARKERS,
    COMPOSE_JS_MARKERS,
    control_room_bundle_errors,
    packaged_control_room_errors,
    served_control_room_errors,
)

ROOT = Path(__file__).resolve().parents[2]


def test_compose_frontend_runs_the_vite_control_room():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "working_dir: /app/frontend" in compose
    assert "npm run dev" in compose
    assert (ROOT / "frontend" / "src" / "main.tsx").is_file()
    assert (ROOT / "frontend" / "src" / "styles" / "control-room.css").is_file()


def test_vite_entry_imports_the_same_css_compose_serves():
    source = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert "styles/control-room.css" in source


def test_compose_control_room_source_has_login_and_dark_theme():
    login = (ROOT / "frontend" / "src" / "components" / "LoginForm.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "src" / "styles" / "control-room.css").read_text(encoding="utf-8")
    errors = control_room_bundle_errors([login, css])
    assert errors == []
    for marker in COMPOSE_JS_MARKERS:
        assert marker in login
    for marker in COMPOSE_CSS_MARKERS:
        assert marker in css


def test_control_room_markers_survive_vite_minification():
    minified = "html{color-scheme:dark}.login-page{min-height:100vh}.login-card{padding:24px}"
    js = 'h1:"Control room",p:"Sign in to operate boards and approval gates.",className:"login-page"'
    assert control_room_bundle_errors([minified, js]) == []


def _write_control_room_dist(dist: Path) -> None:
    dist.mkdir()
    index = (
        '<html><head><link rel="stylesheet" href="/assets/index.css"></head><body><div id="root"></div></body></html>'
    )
    css = "html { color-scheme: dark; }\n.login-page { min-height: 100vh; }\n.login-card { padding: 24px; }\n"
    js = 'document.body.innerHTML = "<h1>Control room</h1><div class=\\"login-page\\">Sign in to operate boards and approval gates.</div>"'
    with zipfile.ZipFile(dist / "norns_ide-0.0.1-py3-none-any.whl", "w") as archive:
        archive.writestr("norns/web/index.html", index)
        archive.writestr("norns/web/assets/index.css", css)
        archive.writestr("norns/web/assets/index.js", js)
    with tarfile.open(dist / "norns_ide-0.0.1.tar.gz", "w:gz") as archive:
        for name, payload in (
            ("norns_ide-0.0.1/norns/web/index.html", index.encode()),
            ("norns_ide-0.0.1/norns/web/assets/index.css", css.encode()),
            ("norns_ide-0.0.1/norns/web/assets/index.js", js.encode()),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def test_check_dist_accepts_compose_matching_control_room(tmp_path: Path):
    dist = tmp_path / "dist"
    _write_control_room_dist(dist)
    completed = subprocess.run([sys.executable, str(ROOT / "scripts" / "check-dist.py"), str(dist)], check=False)
    assert completed.returncode == 0


def test_check_dist_rejects_cssless_dist_like_stale_docker_build(tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    html = "<html><script src='/assets/index.js'></script><div id='root'></div></html>"
    js = 'console.log("manage boards")'
    with zipfile.ZipFile(dist / "norns_ide-0.0.1-py3-none-any.whl", "w") as archive:
        archive.writestr("norns/web/index.html", html)
        archive.writestr("norns/web/assets/index.js", js)
    with tarfile.open(dist / "norns_ide-0.0.1.tar.gz", "w:gz") as archive:
        for name, payload in (
            ("norns_ide-0.0.1/norns/web/index.html", html.encode()),
            ("norns_ide-0.0.1/norns/web/assets/index.js", js.encode()),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    completed = subprocess.run([sys.executable, str(ROOT / "scripts" / "check-dist.py"), str(dist)], check=False)
    assert completed.returncode == 1


def test_served_ui_matches_compose_login():
    assets = {
        "/assets/index.css": "html{color-scheme:dark}.login-page{}.login-card{}",
        "/assets/index.js": ('h1:"Control room";p:"Sign in to operate boards and approval gates.";class:"login-page"'),
    }
    html = (
        '<html><head><link rel="stylesheet" href="/assets/index.css">'
        '<script src="/assets/index.js"></script></head><body><div id="root"></div></body></html>'
    )
    assert served_control_room_errors(html, assets.__getitem__) == []


def test_served_ui_rejects_cssless_login():
    html = '<html><script src="/assets/index.js"></script><div id="root"></div></html>'
    errors = served_control_room_errors(html, lambda href: 'console.log("manage boards")')
    assert errors


def test_packaged_web_matches_compose_when_staged():
    web = ROOT / "norns" / "web"
    if not (web / "index.html").is_file():
        pytest.skip("Control Room not staged; CI package job builds the wheel")
    errors = packaged_control_room_errors(web)
    assert errors == []
