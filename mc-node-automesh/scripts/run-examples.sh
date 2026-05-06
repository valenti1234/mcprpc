#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-dev}"
REGISTRY_URL="${REGISTRY_URL:-http://localhost:7000}"
SERVICE_NAME="${SERVICE_NAME:-node-billing-worker}"
ENDPOINT="${ENDPOINT:-node dist/examples/billing-worker.js}"

if [ ! -d node_modules ]; then
  npm install
fi

if command -v curl >/dev/null 2>&1; then
  if ! curl -fsS "${REGISTRY_URL%/}/health" >/dev/null 2>&1; then
    echo "warning: registry health check failed at ${REGISTRY_URL%/}/health" >&2
  fi
fi

export REGISTRY_URL
export SERVICE_NAME
export ENDPOINT

case "$MODE" in
  dev)
    npm run dev
    ;;
  test)
    npm run test
    ;;
  build)
    npm run build
    ;;
  *)
    echo "usage: $(basename "$0") [dev|test|build]" >&2
    exit 2
    ;;
esac
