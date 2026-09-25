#!/usr/bin/env bash
# Install norns-ide from TestPyPI (or a local wheel) and run a lean real-user acceptance path.
#
# Usage:
#   bash scripts/acceptance_testpypi.sh
#   bash scripts/acceptance_testpypi.sh --version 0.0.3
#   bash scripts/acceptance_testpypi.sh --wheel dist/norns_ide-0.0.3-py3-none-any.whl
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION=""
WHEEL=""
PORT="${NORNS_ACCEPTANCE_PORT:-8765}"
KEEP_VENV=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="${2:?}"
      shift 2
      ;;
    --wheel)
      WHEEL="${2:?}"
      shift 2
      ;;
    --port)
      PORT="${2:?}"
      shift 2
      ;;
    --keep-venv)
      KEEP_VENV=1
      shift
      ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

WORKDIR="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/norns-acceptance-$$"
VENV="$WORKDIR/venv"
HOME_DIR="$WORKDIR/norns-home"
mkdir -p "$WORKDIR"
cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  if [[ "$KEEP_VENV" -eq 0 ]]; then
    rm -rf "$WORKDIR"
  else
    echo "Kept workdir: $WORKDIR"
  fi
}
trap cleanup EXIT

python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install -U pip

if [[ -n "$WHEEL" ]]; then
  echo "==> Installing local wheel: $WHEEL"
  python -m pip install "$WHEEL"
else
  SPEC="norns-ide"
  if [[ -n "$VERSION" ]]; then
    SPEC="norns-ide==${VERSION}"
  fi
  echo "==> Downloading $SPEC from TestPyPI (no deps — TestPyPI stubs break fastapi/etc.)"
  WHEEL_DIR="$WORKDIR/wheels"
  mkdir -p "$WHEEL_DIR"
  python -m pip download --no-deps -i https://test.pypi.org/simple/ -d "$WHEEL_DIR" "$SPEC"
  # Resolve runtime deps from real PyPI while installing the TestPyPI wheel.
  echo "==> Installing TestPyPI wheel + deps from PyPI"
  python -m pip install --no-cache-dir "$WHEEL_DIR"/norns_ide-*.whl
fi

echo "==> norns --version"
norns --version
python -c "import norns; print('package', norns.__version__)"

echo "==> norns init"
norns init --home "$HOME_DIR"

# Point the local server at our chosen port without editing config.toml by hand.
# apply_config reads [server] port; override via CLI.
echo "==> norns run (no window) on port $PORT"
norns run --home "$HOME_DIR" --port "$PORT" --no-window &
SERVER_PID=$!

BASE="http://127.0.0.1:${PORT}"
echo "==> wait for health at $BASE"
ok=0
for _ in $(seq 1 60); do
  if curl -fsS "$BASE/api/health" >/dev/null; then
    ok=1
    break
  fi
  sleep 0.25
done
if [[ "$ok" -ne 1 ]]; then
  echo "Server did not become healthy" >&2
  exit 1
fi

echo "==> served UI check"
# Prefer repo helper when present (CI checkout); else skip if only TestPyPI install.
if [[ -f "$ROOT/scripts/check-served-ui.py" ]]; then
  python "$ROOT/scripts/check-served-ui.py" "$BASE"
else
  curl -fsS "$BASE/" | grep -qi "norns\|login\|control" || {
    echo "UI root did not look like Control Room" >&2
    exit 1
  }
  echo "OK basic UI fetch (no check-served-ui.py in PATH)"
fi

echo "==> HTTP acceptance (login → board → sample card → prefs → logout)"
python "$ROOT/scripts/acceptance_http.py" --base "$BASE" --home "$HOME_DIR"

echo "==> DONE TestPyPI/local acceptance"
