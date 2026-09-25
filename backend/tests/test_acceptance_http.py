"""Unit checks for the TestPyPI acceptance HTTP helper (no live server)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "acceptance_http.py"


def _load_acceptance_http():
    spec = importlib.util.spec_from_file_location("acceptance_http", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["acceptance_http"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_admin_password_reads_config(tmp_path: Path):
    mod = _load_acceptance_http()
    home = tmp_path / "norns"
    home.mkdir()
    (home / "config.toml").write_text(
        '[auth]\nadmin_username = "admin"\nadmin_password = "secret-pass"\n',
        encoding="utf-8",
    )
    assert mod.admin_password(home) == "secret-pass"


def test_admin_password_missing(tmp_path: Path):
    mod = _load_acceptance_http()
    home = tmp_path / "norns"
    home.mkdir()
    (home / "config.toml").write_text('[auth]\nadmin_username = "admin"\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        mod.admin_password(home)
