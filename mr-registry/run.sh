#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

. .venv/bin/activate

python -m pip install -U pip >/dev/null
pip install -e ".[dev]" >/dev/null

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-7000}"
LOG_LEVEL="${LOG_LEVEL:-info}"
MCPRPC_LOG_INVALID_HTTP="${MCPRPC_LOG_INVALID_HTTP:-0}"
export MCPRPC_REGISTRY_RESET_DB_ON_START="${MCPRPC_REGISTRY_RESET_DB_ON_START:-1}"

if [ "$MCPRPC_LOG_INVALID_HTTP" = "1" ]; then
  UPSTREAM_PORT="${UPSTREAM_PORT:-$((PORT + 1))}"
  UPSTREAM_HOST="${UPSTREAM_HOST:-127.0.0.1}"
  SNIFF_BYTES="${SNIFF_BYTES:-2048}"
  RELOAD="${RELOAD:-1}"
  export UPSTREAM_PORT UPSTREAM_HOST SNIFF_BYTES RELOAD
  exec python3 run_with_sniffer.py
fi

exec uvicorn app.main:app --reload --host "$HOST" --port "$PORT" --log-level "$LOG_LEVEL"
