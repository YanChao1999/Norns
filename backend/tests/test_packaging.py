from __future__ import annotations

from pathlib import Path

import pytest

from norns_build import stage_control_room


def test_stage_control_room_skips_when_index_exists(tmp_path: Path):
    web = tmp_path / "norns" / "web"
    web.mkdir(parents=True)
    (web / "index.html").write_text("<html></html>", encoding="utf-8")
    assert stage_control_room(tmp_path) == web


def test_stage_control_room_requires_frontend_or_packaged_ui(tmp_path: Path):
    (tmp_path / "norns" / "web").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="Control Room UI is missing"):
        stage_control_room(tmp_path)
