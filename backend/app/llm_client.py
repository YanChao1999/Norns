"""Shared AsyncOpenAI construction with optional system-proxy support."""

from __future__ import annotations

from typing import Any

from .proxy_env import apply_proxy_env_fixes, use_system_proxy


def create_async_openai(**kwargs: Any) -> Any:
    """Build ``AsyncOpenAI`` honoring the user's system-proxy preference.

    When system proxy is on, Clash-style ``socks://`` URLs are normalized to
    ``socks5://``. When off, ``trust_env=False`` so corporate/Clash env vars
    are ignored (direct egress).

    Call sites should close the client (``async with`` or ``await client.close()``).
    """
    from openai import AsyncOpenAI, DefaultAsyncHttpxClient

    if use_system_proxy():
        apply_proxy_env_fixes()
        return AsyncOpenAI(**kwargs)

    http_client = kwargs.pop("http_client", None)
    if http_client is None:
        http_client = DefaultAsyncHttpxClient(trust_env=False)
    return AsyncOpenAI(http_client=http_client, **kwargs)
