"""PlantUML renderer: optional local/remote servers only. Public egress is opt-in."""
from __future__ import annotations

import asyncio
import logging
import zlib

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

_PLANTUML_ALPHABET = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
)


def _encode_plantuml(text: str) -> str:
    data = zlib.compress(text.encode("utf-8"), 9)[2:-4]
    result = []
    buf = 0
    bits = 0
    for byte in data:
        buf = (buf << 8) | byte
        bits += 8
        while bits >= 6:
            bits -= 6
            result.append(_PLANTUML_ALPHABET[(buf >> bits) & 0x3F])
    if bits > 0:
        result.append(_PLANTUML_ALPHABET[(buf << (6 - bits)) & 0x3F])
    return "".join(result)


def _render_via_plantuml_lib_sync(source: str, server_url: str) -> str | None:
    try:
        import plantuml  # type: ignore

        server = plantuml.PlantUML(url=server_url)
        result = server.processes(source)
        if isinstance(result, bytes):
            return result.decode("utf-8")
        return result
    except Exception as exc:
        logger.debug("plantuml lib render failed: %s", exc)
        return None


async def _render_via_plantuml_lib(source: str, server_url: str) -> str | None:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _render_via_plantuml_lib_sync, source, server_url)


async def _render_via_kroki(source: str, kroki_base: str) -> str | None:
    try:
        encoded = _encode_plantuml(source)
        url = f"{kroki_base.rstrip('/')}/plantuml/svg/{encoded}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.debug("Kroki render failed: %s", exc)
        return None


def _placeholder_svg() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="60">'
        '<rect width="400" height="60" fill="#fff3cd" rx="4"/>'
        '<text x="10" y="35" font-family="monospace" font-size="13" fill="#856404">'
        "PlantUML render unavailable"
        "</text></svg>"
    )


async def render_plantuml(source: str) -> str:
    """Render PlantUML to SVG using configured servers only.

    Set PLANTUML_URL and/or KROKI_URL to enable rendering. Unset means no egress.
    """
    settings = get_settings()
    if settings.plantuml_url:
        svg = await _render_via_plantuml_lib(source, settings.plantuml_url)
        if svg:
            return svg
    if settings.kroki_url:
        svg = await _render_via_kroki(source, settings.kroki_url)
        if svg:
            return svg
    if not settings.plantuml_url and not settings.kroki_url:
        logger.info("PlantUML/Kroki URLs are unset; skipping remote render.")
    else:
        logger.warning("Configured PlantUML renderers failed; returning placeholder SVG.")
    return _placeholder_svg()
