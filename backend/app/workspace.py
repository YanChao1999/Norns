from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models.connector import Connector, ConnectorType


@dataclass(frozen=True, slots=True)
class Workspace:
    """Git workplace for a board or a single stage agent: local checkout and/or remote URL."""

    path: str = ""
    git_url: str = ""
    source: str = ""

    @property
    def github_repo(self) -> str:
        return github_repo_from_url(self.git_url)

    def is_local_git(self) -> bool:
        root = Path(self.path) if self.path else None
        return bool(root and root.is_dir() and (root / ".git").exists())


def github_repo_from_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    text = re.sub(r"\.git$", "", text)
    match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/#?]+)", text, re.I)
    if match:
        return f"{match.group('owner')}/{match.group('repo')}"
    if re.match(r"^[^/]+/[^/]+$", text):
        return text
    return ""


def detect_git_root(start: str | Path | None) -> str:
    current = Path(start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return str(candidate)
    return ""


def git_remote_url(root: str) -> str:
    git_config = Path(root) / ".git" / "config"
    if not git_config.is_file():
        return ""
    try:
        text = git_config.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    match = re.search(r'\[remote "origin"\][^\[]*url\s*=\s*(\S+)', text)
    return match.group(1).strip() if match else ""


def workspace_fields(obj: Any | None) -> tuple[str, str]:
    if obj is None:
        return "", ""
    path = str(getattr(obj, "workspace_path", "") or "").strip()
    git_url = str(getattr(obj, "git_url", "") or "").strip()
    return path, git_url


def resolve_workspace(
    connectors: list[Connector] | None = None,
    *,
    agent: Any | None = None,
    board: Any | None = None,
    cwd: str | None = None,
) -> Workspace:
    """Pick the git workplace: this agent, then this board, then legacy connector/env/cwd."""
    agent_path, agent_url = workspace_fields(agent)
    if agent_path or agent_url:
        return _fill_workspace(agent_path, agent_url, source="agent")

    board_path, board_url = workspace_fields(board)
    if board_path or board_url:
        return _fill_workspace(board_path, board_url, source="board")

    for connector in connectors or []:
        if connector.connector_type != ConnectorType.WORKSPACE or not connector.is_active:
            continue
        config = connector.get_config()
        path = str(config.get("path") or "").strip()
        git_url = str(config.get("git_url") or "").strip()
        if path or git_url:
            return _fill_workspace(path, git_url, source=f"connector:{connector.name}")

    for connector in connectors or []:
        if connector.connector_type != ConnectorType.CURSOR or not connector.is_active:
            continue
        config = connector.get_config()
        path = str(config.get("workspace_path") or "").strip()
        git_url = str(config.get("repo_url") or "").strip()
        if path or git_url:
            return _fill_workspace(path, git_url, source="cursor")

    env_path = str(os.environ.get("NORNS_WORKSPACE") or "").strip()
    env_url = str(os.environ.get("NORNS_GIT_URL") or "").strip()
    if env_path or env_url:
        return _fill_workspace(env_path, env_url, source="env")

    detected = detect_git_root(cwd)
    if detected:
        return _fill_workspace(detected, git_remote_url(detected), source="cwd")
    return Workspace()


def serialize_workspace(found: Workspace) -> dict[str, object]:
    return {
        "path": found.path or None,
        "git_url": found.git_url or None,
        "github_repo": found.github_repo or None,
        "source": found.source or None,
        "is_local_git": found.is_local_git(),
    }


def _fill_workspace(path: str, git_url: str, *, source: str) -> Workspace:
    resolved_path = str(Path(path).expanduser()) if path else ""
    if resolved_path and Path(resolved_path).is_dir() and not git_url:
        git_url = git_remote_url(resolved_path)
    if not resolved_path and git_url:
        detected = detect_git_root(Path.cwd())
        if detected and github_repo_from_url(git_remote_url(detected)) == github_repo_from_url(git_url):
            resolved_path = detected
    return Workspace(path=resolved_path, git_url=git_url, source=source)
