"""System proxy preference and Clash-style ``socks://`` normalization for httpx.

Clash and similar tools often export ``socks://host:port``. httpx / OpenAI httpx2
only accept ``socks5://`` / ``socks5h://`` (and need the ``socksio`` package).

Company and campus networks vary: some require ``HTTP_PROXY`` / ``ALL_PROXY``,
others break when a local Clash proxy is inherited. Users choose via Settings
(or ``USE_SYSTEM_PROXY`` / ``~/.norns/preferences.json`` / ``config.toml``).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from collections.abc import MutableMapping
from pathlib import Path

logger = logging.getLogger("norns")

_PROXY_ENV_KEYS = (
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
)

_PREFS_FILENAME = "preferences.json"
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


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


def _parse_bool(raw: object, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    text = str(raw or "").strip().lower()
    if not text:
        return default
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return default


def preferences_path(home: Path | str | None = None) -> Path | None:
    """``~/.norns/preferences.json`` when a Norns home is known."""
    if home is not None:
        return Path(home).expanduser().resolve() / _PREFS_FILENAME
    override = os.environ.get("NORNS_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve() / _PREFS_FILENAME
    return None


def load_preferences(path: Path | None = None) -> dict:
    target = path if path is not None else preferences_path()
    if target is None or not target.is_file():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_preferences(updates: dict, *, path: Path | None = None) -> dict:
    """Merge *updates* into preferences.json (creates file under NORNS_HOME when set)."""
    target = path if path is not None else preferences_path()
    if target is None:
        raise FileNotFoundError("NORNS_HOME is not set; cannot persist preferences")
    current = load_preferences(target)
    current.update(updates)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        target.chmod(0o600)
    return current


def use_system_proxy() -> bool:
    """Whether LLM/HTTP clients should honor ``HTTP(S)_PROXY`` / ``ALL_PROXY``.

    Precedence: process env ``USE_SYSTEM_PROXY`` → preferences.json → default True
    (so Clash/corporate proxies keep working until the user opts out).
    """
    if "USE_SYSTEM_PROXY" in os.environ:
        return _parse_bool(os.environ.get("USE_SYSTEM_PROXY"), True)
    prefs = load_preferences()
    if "use_system_proxy" in prefs:
        return _parse_bool(prefs.get("use_system_proxy"), True)
    return True


def set_use_system_proxy(enabled: bool, *, persist: bool = True) -> bool:
    """Apply the preference for this process; optionally write preferences.json."""
    flag = bool(enabled)
    os.environ["USE_SYSTEM_PROXY"] = "true" if flag else "false"
    if persist:
        try:
            save_preferences({"use_system_proxy": flag})
        except FileNotFoundError:
            logger.info("USE_SYSTEM_PROXY=%s (not persisted; NORNS_HOME unset)", flag)
    if flag:
        apply_proxy_env_fixes()
    try:
        from .config import get_settings

        get_settings.cache_clear()
    except Exception:  # noqa: BLE001 — avoid import cycles / cold start issues
        pass
    return flag


def proxy_env_snapshot(environ: MutableMapping[str, str] | None = None) -> dict[str, str]:
    """Non-secret proxy URL values currently visible in the environment."""
    env = os.environ if environ is None else environ
    out: dict[str, str] = {}
    for key in _PROXY_ENV_KEYS:
        value = str(env.get(key, "") or "").strip()
        if value:
            out[key] = value
    return out


def httpx_trust_env() -> bool:
    """Pass to ``httpx.AsyncClient(trust_env=...)`` and OpenAI's DefaultAsyncHttpxClient."""
    enabled = use_system_proxy()
    if enabled:
        apply_proxy_env_fixes()
    return enabled
