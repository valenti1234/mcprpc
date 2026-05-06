#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_DIR}/.venv"

REGISTRY_URL="${1:-${AUTOMESH_REGISTRY_URL:-http://localhost:7000}}"
SERVICE_NAME="${2:-${AUTOMESH_SERVICE_NAME:-billing-service}}"
ENTRYPOINT="${3:-${AUTOMESH_ENTRYPOINT:-${REPO_DIR}/example/main.py}}"

cd "${REPO_DIR}"

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"
python -m pip install -U pip
python -m pip install -e .

export PYTHONPATH="${REPO_DIR}/src"
export AUTOMESH_REGISTRY_URL="${REGISTRY_URL}"
export AUTOMESH_SERVICE_NAME="${SERVICE_NAME}"
export AUTOMESH_TRANSPORT="${AUTOMESH_TRANSPORT:-sse}"
if [[ "${AUTOMESH_TRANSPORT}" == "sse" ]]; then
  if [[ -z "${AUTOMESH_ENDPOINT:-}" ]]; then
    AUTOMESH_SSE_PORT="${AUTOMESH_SSE_PORT:-}"
    if [[ -z "${AUTOMESH_SSE_PORT}" ]]; then
      AUTOMESH_SSE_PORT="$(python - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
port = s.getsockname()[1]
s.close()
print(port)
PY
)"
    fi
    export AUTOMESH_ENDPOINT="http://localhost:${AUTOMESH_SSE_PORT}/sse/"
  fi
else
  export AUTOMESH_ENDPOINT="${AUTOMESH_ENDPOINT:-}"
fi

python "${ENTRYPOINT}"
