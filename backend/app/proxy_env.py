"""Normalize proxy environment variables for httpx / OpenAI httpx2.

Clash and similar local proxies often export ``socks://host:port``. httpx and
httpx2 only accept ``socks5://`` / ``socks5h://`` (and require the ``socksio``
package). Leaving ``socks://`` in the environment makes ``AsyncOpenAI()`` fail
during construction and can leave a half-initialized client whose ``aclose``
raises ``AttributeError: ... no attribute '_transport'``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import MutableMapping

logger = logging.getLogger("norns")

_PROXY_ENV_KEYS = (
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
)


def normalize_proxy_url(url: str) -> str:
    """Map Clash-style ``socks://`` to httpx-compatible ``socks5://``."""
    raw = str(url or "").strip()
    if not raw:
        return raw
    lower = raw.lower()
    if lower.startswith("socks://"):
        return "socks5://" + raw[len("socks://") :]
    return raw


def apply_proxy_env_fixes(environ: MutableMapping[str, str] | None = None) -> list[tuple[str, str]]:
    """Rewrite unsupported socks proxy URLs in *environ* (default: ``os.environ``).

    Returns ``(key, previous_value)`` pairs that were changed.
    """
    env = os.environ if environ is None else environ
    changed: list[tuple[str, str]] = []
    for key in _PROXY_ENV_KEYS:
        if key not in env:
            continue
        old = env[key]
        new = normalize_proxy_url(old)
        if new != old:
            env[key] = new
            changed.append((key, old))
    if changed:
        logger.info(
            "Normalized proxy URL scheme socks:// → socks5:// for %s",
            ", ".join(key for key, _ in changed),
        )
    return changed
