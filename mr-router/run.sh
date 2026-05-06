#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

. .venv/bin/activate

python -m pip install -U pip >/dev/null
pip install -e ".[test]" >/dev/null

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-7010}"
export REGISTRY_URL="${REGISTRY_URL:-http://localhost:7000}"
export MCPRPC_STDIO_PERSISTENT="${MCPRPC_STDIO_PERSISTENT:-1}"

exec uvicorn app.main:app --reload --host "$HOST" --port "$PORT"
