from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Naive UTC timestamp for DateTime(timezone=False) columns."""
    return datetime.now(UTC).replace(tzinfo=None)
