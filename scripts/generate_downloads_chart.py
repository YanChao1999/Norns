#!/usr/bin/env python3
"""Generate assets/downloads-trend.svg from PyPI download stats (pypistats.org)."""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

PACKAGE = "norns-ide"
STATS_URL = f"https://pypistats.org/api/packages/{PACKAGE}/overall?mirrors=true"


def fetch_daily_downloads() -> list[tuple[str, int]]:
    with urllib.request.urlopen(STATS_URL, timeout=30) as response:
        payload = json.load(response)
    rows = [
        (str(item["date"]), int(item["downloads"]))
        for item in payload.get("data", [])
        if item.get("category") == "with_mirrors"
    ]
    rows.sort(key=lambda item: item[0])
    return rows[-90:]


def render_svg(rows: list[tuple[str, int]]) -> str:
    if not rows:
        raise ValueError("no download rows returned from pypistats")

    width, height = 720, 220
    pad_l, pad_r, pad_t, pad_b = 48, 16, 28, 40
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    max_y = max(value for _, value in rows) or 1
    count = len(rows)

    def x_at(index: int) -> float:
        if count == 1:
            return pad_l + plot_w / 2
        return pad_l + plot_w * index / (count - 1)

    def y_at(value: int) -> float:
        return pad_t + plot_h * (1 - value / max_y)

    points = " ".join(f"{x_at(i):.1f},{y_at(value):.1f}" for i, (_, value) in enumerate(rows))
    area = f"{pad_l:.1f},{pad_t + plot_h:.1f} " + points + f" {x_at(count - 1):.1f},{pad_t + plot_h:.1f}"

    tick_indexes: list[int] = []
    seen_months: set[str] = set()
    for index, (day, _) in enumerate(rows):
        month = day[:7]
        if month not in seen_months:
            seen_months.add(month)
            tick_indexes.append(index)
    if tick_indexes[-1] != count - 1:
        tick_indexes.append(count - 1)

    tick_svg: list[str] = []
    for index in tick_indexes:
        day, _ = rows[index]
        x = x_at(index)
        label = datetime.strptime(day, "%Y-%m-%d").strftime("%b %d")
        tick_svg.append(
            f'<line x1="{x:.1f}" y1="{pad_t + plot_h:.1f}" x2="{x:.1f}" y2="{pad_t + plot_h + 6:.1f}" '
            f'stroke="#94a3b8" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="{height - 12}" text-anchor="middle" font-size="11" fill="#64748b" '
            f'font-family="ui-sans-serif,system-ui,sans-serif">{label}</text>'
        )

    y_labels: list[str] = []
    for fraction, value in ((0.0, max_y), (0.5, max_y // 2), (1.0, 0)):
        y = pad_t + plot_h * fraction
        y_labels.append(
            f'<text x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="#64748b" '
            f'font-family="ui-sans-serif,system-ui,sans-serif">{value}</text>'
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1"/>'
        )

    last_value = rows[-1][1]
    month_total = sum(value for _, value in rows[-30:])
    updated = datetime.now(UTC).strftime("%Y-%m-%d UTC")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{PACKAGE} PyPI downloads trend">
  <title>{PACKAGE} PyPI downloads (daily)</title>
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{pad_l}" y="18" font-size="13" font-weight="600" fill="#0f172a" font-family="ui-sans-serif,system-ui,sans-serif">{PACKAGE} PyPI downloads · daily</text>
  <text x="{width - pad_r}" y="18" text-anchor="end" font-size="11" fill="#64748b" font-family="ui-sans-serif,system-ui,sans-serif">last day {last_value} · ~30d {month_total} · updated {updated}</text>
  {"".join(y_labels)}
  <polygon points="{area}" fill="#38bdf8" fill-opacity="0.18"/>
  <polyline points="{points}" fill="none" stroke="#0284c7" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="{x_at(count - 1):.1f}" cy="{y_at(last_value):.1f}" r="3.5" fill="#0284c7"/>
  {"".join(tick_svg)}
</svg>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/downloads-trend.svg"),
        help="SVG path relative to the repo root",
    )
    args = parser.parse_args()
    rows = fetch_daily_downloads()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_svg(rows), encoding="utf-8")
    print(f"wrote {args.output} ({len(rows)} days)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
