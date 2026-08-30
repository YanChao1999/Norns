from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

# Same strings docker compose serves via Vite (`frontend/` + `npm run dev`).
COMPOSE_JS_MARKERS = (
    "Control room",
    "Sign in to operate boards and approval gates.",
    "login-page",
)
COMPOSE_CSS_MARKERS = (
    "color-scheme: dark",
    ".login-page",
    ".login-card",
)

_ASSET_REF = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+\.(?:css|js))["']""", re.IGNORECASE)


def ui_is_complete(root: Path) -> bool:
    """A Vite build is only the Control Room if index.html plus a stylesheet exist."""
    index = root / "index.html"
    if not index.is_file():
        return False
    html = index.read_text(encoding="utf-8", errors="ignore")
    if 'rel="stylesheet"' in html or ".css" in html:
        return True
    assets = root / "assets"
    return assets.is_dir() and any(assets.glob("*.css"))


def _contains_marker(blob: str, marker: str) -> bool:
    if marker in blob:
        return True
    return "".join(marker.split()) in "".join(blob.split())


def control_room_bundle_errors(texts: list[str]) -> list[str]:
    blob = "\n".join(texts)
    errors: list[str] = []
    for marker in (*COMPOSE_JS_MARKERS, *COMPOSE_CSS_MARKERS):
        if not _contains_marker(blob, marker):
            errors.append(f"missing {marker!r}")
    return errors


def packaged_control_room_errors(root: Path) -> list[str]:
    if not ui_is_complete(root):
        return ["UI is missing a stylesheet (that is the unstyled login docker compose does not show)"]
    texts: list[str] = []
    for path in root.rglob("*"):
        if path.suffix.lower() in {".html", ".js", ".css"}:
            texts.append(path.read_text(encoding="utf-8", errors="ignore"))
    return control_room_bundle_errors(texts)


def served_control_room_errors(index_html: str, fetch: Callable[[str], str]) -> list[str]:
    if 'id="root"' not in index_html and "id='root'" not in index_html:
        return ['index.html is missing id="root"']
    hrefs = _ASSET_REF.findall(index_html)
    if not any(href.endswith(".css") for href in hrefs):
        return ["index.html does not link a stylesheet (unstyled login)"]
    texts = [index_html]
    for href in hrefs:
        texts.append(fetch(href))
    return control_room_bundle_errors(texts)


def discover_ui_dir() -> Path | None:
    here = Path(__file__).resolve()
    roots = [
        here.parents[2] / "norns" / "web",
        here.parents[2] / "frontend" / "dist",
        here.parent / "web",
    ]
    try:
        import norns as norns_pkg

        roots.insert(0, Path(norns_pkg.__file__).resolve().parent / "web")
    except ImportError:
        pass
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if ui_is_complete(resolved):
            return resolved
    return None
