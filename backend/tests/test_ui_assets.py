from __future__ import annotations

from pathlib import Path

from backend.app.ui_assets import packaged_control_room_errors, ui_is_complete


def test_ui_is_complete_requires_stylesheet(tmp_path: Path):
    (tmp_path / "index.html").write_text("<html><body><div id='root'></div></body></html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index.js").write_text("console.log(1)", encoding="utf-8")
    assert ui_is_complete(tmp_path) is False


def test_ui_is_complete_when_css_linked(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        '<html><head><link rel="stylesheet" href="/assets/index.css"></head><body></body></html>',
        encoding="utf-8",
    )
    assert ui_is_complete(tmp_path) is True


def test_packaged_control_room_errors_require_compose_login(tmp_path: Path):
    (tmp_path / "index.html").write_text(
        '<html><head><link rel="stylesheet" href="/assets/index.css"></head><body><div id="root"></div></body></html>',
        encoding="utf-8",
    )
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index.css").write_text("html{color-scheme:dark}.login-page{}.login-card{}", encoding="utf-8")
    (assets / "index.js").write_text(
        'h1:"Control room";p:"Sign in to operate boards and approval gates.";class:"login-page"',
        encoding="utf-8",
    )
    assert packaged_control_room_errors(tmp_path) == []


def test_packaged_control_room_errors_on_cssless_tree(tmp_path: Path):
    (tmp_path / "index.html").write_text("<html><body><div id='root'></div></body></html>", encoding="utf-8")
    assert packaged_control_room_errors(tmp_path)
