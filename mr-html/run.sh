#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-8386}"
HOST="${HOST:-0.0.0.0}"

print_usage() {
  cat <<'USAGE'
Usage:
  ./run.sh
  ./run.sh --port 8386 --host 127.0.0.1
  PORT=8386 HOST=127.0.0.1 ./run.sh
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--port)
      PORT="${2:-}"
      shift 2
      ;;
    -h|--host)
      HOST="${2:-}"
      shift 2
      ;;
    --help)
      print_usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      print_usage >&2
      exit 2
      ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found in PATH" >&2
  exit 1
fi

if command -v ss >/dev/null 2>&1; then
  if ss -ltn "( sport = :${PORT} )" 2>/dev/null | awk 'NR>1 {print; exit 0}' | grep -q .; then
    echo "Port ${PORT} is already in use." >&2
    ss -ltn "( sport = :${PORT} )" || true
    exit 1
  fi
fi

OPEN_HOST="${HOST}"
if [[ "${OPEN_HOST}" == "0.0.0.0" || "${OPEN_HOST}" == "::" || "${OPEN_HOST}" == "[::]" ]]; then
  OPEN_HOST="127.0.0.1"
fi

echo "Serving mr-html (bind=${HOST}:${PORT})"
echo "Open: http://${OPEN_HOST}:${PORT}/"
exec python3 -m http.server "${PORT}" --bind "${HOST}"
