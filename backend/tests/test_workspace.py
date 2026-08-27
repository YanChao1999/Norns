from __future__ import annotations

from pathlib import Path

from backend.app.models.board import AgentConfig, Board
from backend.app.models.connector import Connector, ConnectorType
from backend.app.workspace import github_repo_from_url, resolve_workspace


def test_github_repo_from_url():
    assert github_repo_from_url("https://github.com/YanChao1999/Norns.git") == "YanChao1999/Norns"
    assert github_repo_from_url("git@github.com:YanChao1999/Norns.git") == "YanChao1999/Norns"
    assert github_repo_from_url("YanChao1999/Norns") == "YanChao1999/Norns"


def _git_repo(root: Path, url: str) -> Path:
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text(f'[remote "origin"]\n\turl = {url}\n', encoding="utf-8")
    return root


def test_resolve_workspace_prefers_agent_over_board(tmp_path: Path):
    board_repo = _git_repo(tmp_path / "board", "https://github.com/acme/board.git")
    agent_repo = _git_repo(tmp_path / "agent", "https://github.com/acme/agent.git")
    board = Board(name="Board", workspace_path=str(board_repo), git_url="")
    agent = AgentConfig(system_prompt="x", workspace_path=str(agent_repo), git_url="")
    workspace = resolve_workspace([], agent=agent, board=board, cwd=tmp_path)
    assert workspace.source == "agent"
    assert workspace.github_repo == "acme/agent"
    assert workspace.is_local_git()


def test_resolve_workspace_uses_board_when_agent_empty(tmp_path: Path):
    board_repo = _git_repo(tmp_path / "board", "https://github.com/acme/board.git")
    board = Board(name="Board", workspace_path=str(board_repo), git_url="")
    agent = AgentConfig(system_prompt="x", workspace_path="", git_url="")
    workspace = resolve_workspace([], agent=agent, board=board, cwd=tmp_path)
    assert workspace.source == "board"
    assert workspace.github_repo == "acme/board"


def test_resolve_workspace_connector(tmp_path: Path):
    git = _git_repo(tmp_path / "repo", "https://github.com/acme/app.git")
    connector = Connector(name="App", connector_type=ConnectorType.WORKSPACE, encrypted_config=b"", is_active=True)
    connector.set_config({"path": str(git), "git_url": ""})
    workspace = resolve_workspace([connector], cwd=tmp_path)
    assert workspace.is_local_git()
    assert workspace.github_repo == "acme/app"
    assert workspace.source.startswith("connector")


def test_resolve_workspace_prefers_workspace_over_cwd(tmp_path: Path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    (other / ".git").mkdir()
    monkeypatch.chdir(other)
    connector = Connector(
        name="Remote only", connector_type=ConnectorType.WORKSPACE, encrypted_config=b"", is_active=True
    )
    connector.set_config({"path": "", "git_url": "https://github.com/org/proj"})
    workspace = resolve_workspace([connector], cwd=other)
    assert workspace.git_url.endswith("org/proj") or "org/proj" in workspace.git_url
    assert workspace.github_repo == "org/proj"


def test_board_beats_legacy_connector(tmp_path: Path):
    board_repo = _git_repo(tmp_path / "board", "https://github.com/acme/board.git")
    connector_repo = _git_repo(tmp_path / "legacy", "https://github.com/acme/legacy.git")
    board = Board(name="Board", workspace_path=str(board_repo), git_url="")
    connector = Connector(name="App", connector_type=ConnectorType.WORKSPACE, encrypted_config=b"", is_active=True)
    connector.set_config({"path": str(connector_repo), "git_url": ""})
    workspace = resolve_workspace([connector], board=board, cwd=tmp_path)
    assert workspace.source == "board"
    assert workspace.github_repo == "acme/board"
