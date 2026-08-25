"""Fail unless a running norns server serves the docker compose Control Room login."""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.ui_assets import served_control_room_errors  # noqa: E402


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
    if not base.endswith("/"):
        base += "/"

    def fetch(path: str) -> str:
        url = path if path.startswith("http") else urljoin(base, path.lstrip("/"))
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.read().decode("utf-8", errors="ignore")

    try:
        html = fetch("/")
        errors = served_control_room_errors(html, fetch)
    except urllib.error.URLError as exc:
        print(f"Could not fetch Control Room at {base}: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("Served UI does not match docker compose Control Room: " + "; ".join(errors), file=sys.stderr)
        return 1
    print(f"OK {base} serves the docker compose Control Room UI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
