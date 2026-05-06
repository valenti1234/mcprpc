#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_DIR}/.venv"

ROUTER_URL_DEFAULT="http://localhost:7010"
if [[ $# -ge 1 && -n "${1}" ]]; then
  ROUTER_URL="${1}"
else
  ROUTER_URL="${ROUTER_URL_DEFAULT}"
  if [[ -n "${ROUTER_URL:-}" && "${USE_ENV_ROUTER_URL:-0}" != "1" ]]; then
    echo "run-consumer: ignorando ROUTER_URL da env (${ROUTER_URL}) - usa USE_ENV_ROUTER_URL=1 per abilitarlo" >&2
  elif [[ -n "${ROUTER_URL:-}" && "${USE_ENV_ROUTER_URL:-0}" == "1" ]]; then
    echo "run-consumer: usando ROUTER_URL da env: ${ROUTER_URL}" >&2
    ROUTER_URL="${ROUTER_URL}"
  fi
fi
FUNCTION_NAME="${2:-${FUNCTION:-billing.createInvoice}}"
ARGUMENTS_JSON="${3:-${ARGUMENTS_JSON:-}}"
if [[ -z "${ARGUMENTS_JSON}" ]]; then
  ARGUMENTS_JSON="{}"
fi
ROLES="${4:-${ROLES:-}}"

cd "${REPO_DIR}"

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"
python -m pip install -U pip >/dev/null
python -m pip install -e . >/dev/null

export ROUTER_URL="${ROUTER_URL}"
export FUNCTION="${FUNCTION_NAME}"
export ARGUMENTS_JSON="${ARGUMENTS_JSON}"
export ROLES="${ROLES}"

python "${REPO_DIR}/example/consumer.py"
