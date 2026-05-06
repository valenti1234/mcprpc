#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${SCRIPT_DIR}"
VENV_DIR="${REPO_DIR}/.venv"

PORT="${1:-${GUI_PORT:-8002}}"
HOST="${GUI_HOST:-0.0.0.0}"

REGISTRY_URL="${2:-${REGISTRY_URL:-http://localhost:7000}}"
ROUTER_URL="${3:-${ROUTER_URL:-http://localhost:7010}}"
GUI_TIMEOUT_S="${GUI_TIMEOUT_S:-10.0}"

cd "${REPO_DIR}"

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"
python -m pip install -U pip
python -m pip install -e .

export REGISTRY_URL
export ROUTER_URL
export GUI_TIMEOUT_S

exec python -m uvicorn app.main:app --host "${HOST}" --port "${PORT}" --reload
