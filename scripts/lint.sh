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
  @eslint/js@9 \
  typescript-eslint@8 \
  eslint-plugin-react-hooks@5 \
  eslint-config-prettier@10 \
  globals@15 \
  prettier@3 \
  typescript@5
npx eslint . --max-warnings=0

echo "==> Prettier"
npx prettier --check .
