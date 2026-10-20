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
# Use lockfile deps (eslint 10+). Reinstalling eslint@9 majors here crashes npm
# arborist with "Cannot read properties of null (reading 'edgesOut')".
npm ci
npm run lint

echo "==> Prettier"
npm run format:check
