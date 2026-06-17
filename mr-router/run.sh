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

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-7010}"
export REGISTRY_URL="${REGISTRY_URL:-http://127.0.0.1:7000}"
export MCPRPC_STDIO_PERSISTENT="${MCPRPC_STDIO_PERSISTENT:-1}"
export MCPRPC_CORS_ORIGINS="${MCPRPC_CORS_ORIGINS:-http://127.0.0.1:8386,http://localhost:8386}"

exec uvicorn app.main:app --reload --host "$HOST" --port "$PORT"
