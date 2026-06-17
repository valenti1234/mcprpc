#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

export REGISTRY_URL="${REGISTRY_URL:-}"
export MCP_TRANSPORT="${MCP_TRANSPORT:-sse}"
export MCPRPC_BIND_HOST="${MCPRPC_BIND_HOST:-127.0.0.1}"
if [ -z "${AUTOMESH_ENDPOINT:-}" ]; then
  if [ "$MCP_TRANSPORT" = "streamable-http" ]; then
    export AUTOMESH_ENDPOINT="http://127.0.0.1:7002/mcp"
  else
    export AUTOMESH_ENDPOINT="http://127.0.0.1:7002/sse/"
  fi
fi

echo "Starting mc-java-automesh example (MCP $MCP_TRANSPORT)."
echo "Endpoint: $AUTOMESH_ENDPOINT"
echo "Set REGISTRY_URL=http://127.0.0.1:7000 to publish tools to the registry."

mvn -DskipTests compile exec:java \
  -Dexec.mainClass=io.mcprpc.automesh.examples.BillingApiExampleMain
