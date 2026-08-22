#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

echo "==> Ruff"
ruff check backend worker
ruff format --check backend worker

echo "==> ESLint"
cd frontend
npm install --no-save --no-package-lock \
  eslint@9 \
  @eslint/js \
  typescript-eslint \
  eslint-plugin-react-hooks \
  eslint-config-prettier \
  globals \
  prettier@3 \
  typescript
npx eslint . --max-warnings=0

echo "==> Prettier"
npx prettier --check .
