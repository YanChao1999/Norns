"""Which plugin tools change external systems and may need a human confirm."""

from __future__ import annotations

WRITE_FRAGMENTS = (
    "_create_",
    "_update_",
    "_delete_",
    "_add_",
    "_set_",
    "_transition_",
    "_comment_",
    "_open_pr",
    "create_issue",
    "create_subtask",
    "create_card",
    "create_pull",
)


def is_write_tool(name: str) -> bool:
    tool = str(name or "").strip().lower()
    return any(fragment in tool for fragment in WRITE_FRAGMENTS)
