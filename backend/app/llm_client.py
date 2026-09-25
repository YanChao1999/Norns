"""Shared AsyncOpenAI construction with proxy-env fixes."""

from __future__ import annotations

from typing import Any

from .proxy_env import apply_proxy_env_fixes


def create_async_openai(**kwargs: Any) -> Any:
    """Build ``AsyncOpenAI`` after normalizing Clash-style ``socks://`` proxy URLs.

    Call sites should close the client (``async with`` or ``await client.close()``)
    so httpx2 does not finalize a broken transport in a background task.
    """
    apply_proxy_env_fixes()
    from openai import AsyncOpenAI

    return AsyncOpenAI(**kwargs)
