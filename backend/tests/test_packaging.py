from __future__ import annotations

import io
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

from norns_build import COMPOSE_NODE_IMAGE, docker_build_command, stage_control_room

ROOT = Path(__file__).resolve().parents[2]


def test_pypi_name_is_norns_ide():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["name"] == "norns-ide"
    assert data["project"]["scripts"]["norns"] == "norns.cli:main"


def test_check_dist_rejects_taken_pypi_name(tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    with zipfile.ZipFile(dist / "norns-0.0.1-py3-none-any.whl", "w") as archive:
        archive.writestr("norns/web/index.html", "<html></html>")
    html = b"<html></html>"
    with tarfile.open(dist / "norns-0.0.1.tar.gz", "w:gz") as archive:
        info = tarfile.TarInfo("norns-0.0.1/norns/web/index.html")
        info.size = len(html)
        archive.addfile(info, io.BytesIO(html))
    completed = subprocess.run([sys.executable, str(ROOT / "scripts" / "check-dist.py"), str(dist)], check=False)
    assert completed.returncode == 1


def _complete_index() -> str:
    return (
        '<html><head><link rel="stylesheet" href="/assets/index.css"></head><body><div id="root"></div></body></html>'
    )


def test_stage_control_room_skips_when_complete_ui_exists(tmp_path: Path):
    web = tmp_path / "norns" / "web"
    web.mkdir(parents=True)
    (web / "index.html").write_text(_complete_index(), encoding="utf-8")
    assert stage_control_room(tmp_path) == web


def test_stage_control_room_does_not_treat_cssless_index_as_packaged(tmp_path: Path):
    web = tmp_path / "norns" / "web"
    web.mkdir(parents=True)
    (web / "index.html").write_text("<html></html>", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Control Room UI is missing"):
        stage_control_room(tmp_path)


def test_stage_control_room_copies_complete_dist_without_npm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(_complete_index(), encoding="utf-8")
    (dist / "assets").mkdir()
    (dist / "assets" / "index.css").write_text("html { color-scheme: dark; }", encoding="utf-8")
    (tmp_path / "norns" / "web").mkdir(parents=True)

    def fail_npm(*_args, **_kwargs):
        raise AssertionError("npm should not run when frontend/dist is already complete")

    monkeypatch.setattr("norns_build.subprocess.run", fail_npm)
    dest = stage_control_room(tmp_path)
    assert (dest / "index.html").is_file()
    assert 'rel="stylesheet"' in (dest / "index.html").read_text(encoding="utf-8")


def test_stage_control_room_requires_frontend_or_packaged_ui(tmp_path: Path):
    (tmp_path / "norns" / "web").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="Control Room UI is missing"):
        stage_control_room(tmp_path)


def test_stage_control_room_builds_in_writable_cache_when_checkout_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "norns" / "web").mkdir(parents=True)
    cache = tmp_path / "ui-build"
    monkeypatch.setenv("NORNS_UI_BUILD_DIR", str(cache))
    monkeypatch.setattr("norns_build._can_build_in_place", lambda _frontend: False)
    monkeypatch.setattr("norns_build._npm_executable", lambda: "npm")

    def fake_npm(cmd, cwd, check=False):
        dist = Path(cwd) / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "index.html").write_text(_complete_index(), encoding="utf-8")
        (dist / "assets").mkdir(exist_ok=True)
        (dist / "assets" / "index.css").write_text("html{}", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("norns_build.subprocess.run", fake_npm)
    dest = stage_control_room(tmp_path)
    assert 'rel="stylesheet"' in (dest / "index.html").read_text(encoding="utf-8")
    assert (cache / "package.json").is_file()


def test_compose_frontend_uses_the_same_node_image_as_ui_build():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert COMPOSE_NODE_IMAGE in compose
    assert "npm run dev" in compose


def test_stage_control_room_uses_compose_node_image_when_npm_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "norns" / "web").mkdir(parents=True)
    monkeypatch.setattr("norns_build._npm_executable", lambda: None)
    monkeypatch.setattr("norns_build._docker_executable", lambda: "/usr/bin/docker")
    monkeypatch.setattr("norns_build._can_build_in_place", lambda _frontend: True)
    recorded: dict[str, list[str]] = {}

    def fake_run(cmd, cwd=None, check=False):
        recorded["cmd"] = list(cmd)
        dist = frontend / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        (dist / "index.html").write_text(_complete_index(), encoding="utf-8")
        (dist / "assets").mkdir(exist_ok=True)
        (dist / "assets" / "index.css").write_text("html{}", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("norns_build.subprocess.run", fake_run)
    dest = stage_control_room(tmp_path)
    assert 'rel="stylesheet"' in (dest / "index.html").read_text(encoding="utf-8")
    assert recorded["cmd"][0] == "/usr/bin/docker"
    assert COMPOSE_NODE_IMAGE in recorded["cmd"]
    assert "npm ci && npm run build" in recorded["cmd"]


def test_docker_build_command_errors_when_docker_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr("norns_build._docker_executable", lambda: None)
    with pytest.raises(RuntimeError, match="docker is not available"):
        docker_build_command(tmp_path)


def test_norns_run_loads_norns_build_without_repo_on_sys_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        sys,
        "path",
        [entry for entry in sys.path if entry not in ("", str(ROOT)) and not str(entry).endswith("Norns")],
    )
    sys.modules.pop("norns_build", None)
    from norns.desktop import _load_stage_control_room

    stage = _load_stage_control_room()
    assert stage is not None
    assert stage.__module__ in {"norns_build"}
