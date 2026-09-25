#!/usr/bin/env python3
"""Lean HTTP acceptance against a running ``norns`` server (real-user path).

Assumes ``norns init`` already created *home* and ``norns run`` is listening.
Steps mirror first-run docs with few checks: login → create board → sample card
→ preferences → logout.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path


class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, object]:
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                payload: object = json.loads(raw) if raw.strip() else {}
                return resp.status, payload
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                payload = {"raw": raw[:500]}
            return exc.code, payload


def admin_password(home: Path) -> str:
    path = home / "config.toml"
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    password = str(data.get("auth", {}).get("admin_password", "") or "").strip()
    if not password:
        raise SystemExit(f"No admin_password in {path}")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8765")
    parser.add_argument("--home", type=Path, required=True, help="NORNS_HOME used for norns init")
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    password = admin_password(home)
    client = Client(args.base)

    status, health = client.request("GET", "/api/health")
    if status != 200 or not isinstance(health, dict) or health.get("status") != "ok":
        print(f"FAIL health: {status} {health}", file=sys.stderr)
        return 1
    print("OK health")

    status, _ = client.request("GET", "/api/boards")
    if status != 401:
        print(f"FAIL boards should require auth, got {status}", file=sys.stderr)
        return 1
    print("OK unauthenticated boards → 401")

    status, me = client.request("POST", "/api/auth/login", {"username": "admin", "password": password})
    if status != 200:
        print(f"FAIL login: {status} {me}", file=sys.stderr)
        return 1
    print("OK login")

    status, boards = client.request("GET", "/api/boards")
    if status != 200 or not isinstance(boards, list):
        print(f"FAIL list boards: {status} {boards}", file=sys.stderr)
        return 1
    print(f"OK list boards ({len(boards)})")

    status, board = client.request(
        "POST",
        "/api/boards",
        {"name": "Acceptance", "description": "TestPyPI smoke board"},
    )
    if status not in (200, 201) or not isinstance(board, dict) or not board.get("id"):
        print(f"FAIL create board: {status} {board}", file=sys.stderr)
        return 1
    board_id = str(board["id"])
    print(f"OK create board {board_id}")

    status, detail = client.request("GET", f"/api/boards/{board_id}")
    if status != 200 or not isinstance(detail, dict):
        print(f"FAIL board detail: {status} {detail}", file=sys.stderr)
        return 1
    cards = detail.get("cards") if isinstance(detail.get("cards"), list) else []
    sample = [c for c in cards if isinstance(c, dict) and "practice" in str(c.get("title", "")).lower()]
    if not sample and not cards:
        print(f"FAIL expected sample card on new board, cards={cards!r}", file=sys.stderr)
        return 1
    print(f"OK sample/practice card present ({len(cards)} card(s))")

    status, prefs = client.request("GET", "/api/preferences")
    if status != 200 or not isinstance(prefs, dict) or "use_system_proxy" not in prefs:
        print(f"FAIL preferences: {status} {prefs}", file=sys.stderr)
        return 1
    print(f"OK preferences use_system_proxy={prefs.get('use_system_proxy')}")

    status, _ = client.request("POST", "/api/auth/logout")
    if status not in (200, 204):
        print(f"FAIL logout: {status}", file=sys.stderr)
        return 1
    status, _ = client.request("GET", "/api/boards")
    if status != 401:
        print(f"FAIL after logout boards should be 401, got {status}", file=sys.stderr)
        return 1
    print("OK logout")

    print("ACCEPTANCE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
