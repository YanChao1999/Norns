#!/usr/bin/env bash
set -euo pipefail

# Rebuild frontend/ into norns/web. Does not require host npm: uses PATH npm,
# repo .tools/node, or the same Docker node:20 image as `norns run`.
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
if command -v uv >/dev/null 2>&1; then
  uv run python -c "from norns_build import stage_control_room; stage_control_room(force=True)"
else
  PYTHONPATH="$root" python3 -c "from norns_build import stage_control_room; stage_control_room(force=True)"
fi
echo "Staged UI at $root/norns/web"
