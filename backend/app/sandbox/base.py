from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..workspace import Workspace


@dataclass(frozen=True, slots=True)
class SandboxHandle:
    """Prepared workspace isolation for one agent run."""

    path: str
    backend: str
    source_path: str = ""
    metadata: dict[str, object] | None = None


class SandboxProvider(Protocol):
    """Prepare and tear down an isolated workspace for an agent run."""

    name: str

    def prepare(
        self,
        *,
        run_id: str,
        card_id: str,
        board_id: str,
        source: Workspace,
    ) -> SandboxHandle | None:
        """Return a handle when isolation is applied, or None when skipped."""

    def cleanup(self, handle: SandboxHandle) -> None:
        """Best-effort teardown after the run completes or fails."""
