"""Console logging for ``norns run`` — quiet access noise, loud app failures."""

from __future__ import annotations

import copy
import logging
import re
from typing import Any

from uvicorn.config import LOGGING_CONFIG

# Health/poll/static traffic drowns stage failures in the default uvicorn access log.
_QUIET_ACCESS_PARTS = (
    "/api/health",
    "/favicon.ico",
    "/json/version",
    "/assets/",
)
_QUIET_POLL_RE = re.compile(r'"GET /(?:api/boards/[^"\s]+|api/cards/[^"\s]+/runs) HTTP/[^"]*" 200\b')
_ACCESS_STATUS_RE = re.compile(r'"\s+(\d{3})\b')


def _is_success_access(message: str) -> bool:
    match = _ACCESS_STATUS_RE.search(message)
    return bool(match and match.group(1).startswith("2"))


class QuietAccessFilter(logging.Filter):
    """Drop routine successful Control Room polling and static asset hits from the access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 — never break logging
            return True
        # Keep failed health/static/poll requests visible; only quiet 2xx noise.
        if _is_success_access(message) and any(part in message for part in _QUIET_ACCESS_PARTS):
            return False
        return not _QUIET_POLL_RE.search(message)


def compact_error_for_log(detail: str, *, limit: int = 200) -> str:
    """Shorten provider error blobs (e.g. Cursor's full model catalog) for the console."""
    text = " ".join(str(detail or "").split())
    if not text:
        return ""
    cut = text.find(" Available models:")
    if cut > 0:
        text = f"{text[:cut]} (see run output for available models)"
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def uvicorn_log_config() -> dict[str, Any]:
    """Uvicorn dictConfig: wire ``norns`` to the default handler and quiet access spam."""
    config: dict[str, Any] = copy.deepcopy(LOGGING_CONFIG)
    config.setdefault("filters", {})
    config["filters"]["quiet_access"] = {"()": f"{__name__}.QuietAccessFilter"}
    access = config["handlers"]["access"]
    access["filters"] = ["quiet_access"]
    config["loggers"]["norns"] = {
        "handlers": ["default"],
        "level": "INFO",
        "propagate": False,
    }
    return config
