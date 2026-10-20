#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

echo "==> Ruff"
ruff check backend worker norns norns_build.py scripts/check-dist.py scripts/check-served-ui.py
ruff format --check backend worker norns norns_build.py scripts/check-dist.py scripts/check-served-ui.py

echo "==> Electron shell"
node --check norns/electron/main.js

echo "==> ESLint"
cd frontend
npm ci
npx eslint . --max-warnings=0

echo "==> Prettier"
npx prettier --check .
