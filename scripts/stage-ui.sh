#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/frontend"
npm ci
npm run build

dest="$root/norns/web"
rm -rf "$dest"
mkdir -p "$dest"
cp -a dist/. "$dest/"
echo "Staged UI at $dest"
