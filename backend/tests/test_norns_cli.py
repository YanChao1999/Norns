from __future__ import annotations

import os
from pathlib import Path

from norns.cli import main
from norns.desktop import electron_app_dir, electron_command, electron_install_help
from norns.home import apply_config, config_path, init_home, sqlite_url


def test_init_creates_config(tmp_path: Path):
    home = tmp_path / "norns-home"
    path, password = init_home(home)
    assert path == config_path(home)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "encryption_key" in text
    assert "secret_key" in text
    assert 'backend = "inline"' in text
    assert "[cursor]" in text
    assert "[deepseek]" in text
    assert password
    assert 'admin_password = "admin"' not in text
    assert f'admin_password = "{password}"' in text


def test_init_refuses_to_overwrite(tmp_path: Path):
    home = tmp_path / "norns-home"
    init_home(home)
    try:
        init_home(home)
    except FileExistsError:
        pass
    else:
        raise AssertionError("expected FileExistsError")
    db = home / "norns.db"
    db.write_bytes(b"stale")
    init_home(home, force=True)
    assert not db.exists()


def test_cli_init(tmp_path: Path, capsys):
    home = tmp_path / "home"
    assert main(["init", "--home", str(home)]) == 0
    assert config_path(home).is_file()
    out = capsys.readouterr().out
    assert "Admin password:" in out
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
    assert os.environ["NORNS_ENV"] == "local"
    assert os.environ["CURSOR_BASE_URL"] == "https://api.cursor.com/v1"
    assert os.environ["DEEPSEEK_DEFAULT_MODEL"] == "deepseek-v4-flash"


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


def test_electron_install_help_mentions_optional_electron():
    help_text = electron_install_help()
    assert "optional" in help_text.lower()
    assert "browser" in help_text.lower()
    assert "npm install" in help_text
    assert "Qt" not in help_text
