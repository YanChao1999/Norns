"""PlantUML renderer: local plantuml Python package → Kroki API fallback."""
from __future__ import annotations

import base64
import zlib
import logging
import httpx

logger = logging.getLogger(__name__)

# plantuml encoding alphabet
_PLANTUML_ALPHABET = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
)


def _encode_plantuml(text: str) -> str:
    """Encode PlantUML source to the URL-safe format used by plantuml/kroki."""
    data = zlib.compress(text.encode("utf-8"), 9)[2:-4]
    # 6-bit groups, mapped to plantuml alphabet
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


def _render_via_plantuml_lib(source: str) -> str | None:
    """Try to render using the plantuml Python package."""
    try:
        import plantuml  # type: ignore

        server = plantuml.PlantUML(url="http://www.plantuml.com/plantuml/svg/")
        # plantuml.processes returns SVG bytes/string
        result = server.processes(source)
        if isinstance(result, bytes):
            return result.decode("utf-8")
        return result
    except Exception as exc:
        logger.debug("plantuml lib render failed: %s", exc)
        return None


def _render_via_kroki(source: str) -> str | None:
    """Try to render via Kroki public API."""
    try:
        encoded = _encode_plantuml(source)
        url = f"https://kroki.io/plantuml/svg/{encoded}"
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.debug("Kroki render failed: %s", exc)
        return None


def render_plantuml(source: str) -> str:
    """Render a PlantUML diagram to SVG.

    Tries local plantuml Python package first, then falls back to Kroki API.
    Returns an SVG string, or an error placeholder SVG if both fail.
    """
    svg = _render_via_plantuml_lib(source)
    if svg:
        return svg

    svg = _render_via_kroki(source)
    if svg:
        return svg

    logger.warning("All PlantUML renderers failed; returning placeholder SVG.")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="60">'
        '<rect width="400" height="60" fill="#fff3cd" rx="4"/>'
        '<text x="10" y="35" font-family="monospace" font-size="13" fill="#856404">'
        "PlantUML render unavailable"
        "</text></svg>"
    )
