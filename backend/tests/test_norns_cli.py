from __future__ import annotations

import os
from pathlib import Path

from norns.cli import main
from norns.desktop import electron_app_dir, electron_command, electron_install_help
from norns.home import apply_config, config_path, init_home, sqlite_url


def test_init_creates_config(tmp_path: Path):
    home = tmp_path / "norns-home"
    path = init_home(home)
    assert path == config_path(home)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "encryption_key" in text
    assert "secret_key" in text
    assert 'backend = "inline"' in text


def test_init_refuses_to_overwrite(tmp_path: Path):
    home = tmp_path / "norns-home"
    init_home(home)
    try:
        init_home(home)
    except FileExistsError:
        pass
    else:
        raise AssertionError("expected FileExistsError")
    init_home(home, force=True)


def test_cli_init(tmp_path: Path, capsys):
    home = tmp_path / "home"
    assert main(["init", "--home", str(home)]) == 0
    assert config_path(home).is_file()
    assert main(["init", "--home", str(home)]) == 1
    err = capsys.readouterr().err
    assert "already initialized" in err


def test_apply_config_sets_sqlite_and_inline_queue(tmp_path: Path):
    home = tmp_path / "home"
    init_home(home)
    runtime = apply_config(home)
    assert runtime["host"] == "127.0.0.1"
    assert runtime["port"] == 8765
    assert os.environ["QUEUE_BACKEND"] == "inline"
    assert os.environ["DATABASE_URL"] == sqlite_url(home / "norns.db")
    assert os.environ["NORNS_HOME"] == str(home.resolve())


def test_electron_app_dir_ships_chromium_shell():
    app_dir = electron_app_dir()
    assert app_dir is not None
    main_js = (app_dir / "main.js").read_text(encoding="utf-8")
    assert "BrowserWindow" in main_js
    assert "qt" not in main_js.lower()
    assert "webview" not in main_js.lower()


def test_electron_command_uses_local_binary(tmp_path, monkeypatch):
    app_dir = (tmp_path / "electron").resolve()
    bindir = app_dir / "node_modules" / ".bin"
    bindir.mkdir(parents=True)
    binary = bindir / "electron"
    binary.write_text("", encoding="utf-8")
    binary.chmod(0o755)
    dist = app_dir / "node_modules" / "electron" / "dist"
    dist.mkdir(parents=True)
    (dist / "electron").write_text("", encoding="utf-8")
    (app_dir / "main.js").write_text("/* test */", encoding="utf-8")
    monkeypatch.setenv("NORNS_ELECTRON_APP", str(app_dir))
    monkeypatch.delenv("NORNS_ELECTRON", raising=False)
    assert electron_command() == [str(binary), str(app_dir)]


def test_electron_install_help_mentions_npm():
    help_text = electron_install_help()
    assert "Electron" in help_text
    assert "npm install --prefix norns/electron" in help_text
    assert "Qt" not in help_text
