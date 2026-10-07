#!/usr/bin/env bash
set -euo pipefail

# Keep GitHub Pages preview styling in sync with the product Control Room.
root="$(cd "$(dirname "$0")/.." && pwd)"
src="$root/frontend/src/styles/control-room.css"
dest="$root/docs/control-room.css"

if [[ ! -f "$src" ]]; then
  echo "Missing product stylesheet: $src" >&2
  exit 1
fi

cp "$src" "$dest"
echo "Synced $dest from frontend ($(wc -l < "$dest") lines)"
