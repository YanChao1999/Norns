from __future__ import annotations

import io
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

from norns_build import stage_control_room

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


def test_stage_control_room_skips_when_index_exists(tmp_path: Path):
    web = tmp_path / "norns" / "web"
    web.mkdir(parents=True)
    (web / "index.html").write_text("<html></html>", encoding="utf-8")
    assert stage_control_room(tmp_path) == web


def test_stage_control_room_requires_frontend_or_packaged_ui(tmp_path: Path):
    (tmp_path / "norns" / "web").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="Control Room UI is missing"):
        stage_control_room(tmp_path)
