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

MVN="mvn"
if command -v mvn >/dev/null 2>&1; then
  MVN="mvn"
elif [ -x "./mvnw" ]; then
  MVN="./mvnw"
else
  echo "Error: Maven (mvn) not found." >&2
  echo "Install it (Debian/Ubuntu): sudo apt-get update && sudo apt-get install -y maven" >&2
  echo "Or add Maven Wrapper (mvnw) to this module." >&2
  exit 1
fi

required_java_major="$(sed -n 's:.*<maven.compiler.release>\([0-9][0-9]*\)</maven.compiler.release>.*:\1:p' pom.xml | head -n 1)"
if ! [[ "$required_java_major" =~ ^[0-9]+$ ]]; then
  required_java_major=17
fi

extract_java_major() {
  local version_raw="$1"
  local major="$version_raw"
  if [[ "$major" == 1.* ]]; then
    major="${major#1.}"
    major="${major%%.*}"
  else
    major="${major%%.*}"
  fi
  printf '%s\n' "$major"
}

detect_java_version() {
  java -XshowSettings:properties -version 2>&1 | awk -F'= ' '/^[[:space:]]*java\.version =/ {print $2; exit}'
}

JAVA_VERSION_RAW="$(detect_java_version)"
if [ -z "$JAVA_VERSION_RAW" ]; then
  JAVA_VERSION_RAW="$(java -version 2>&1 | head -n 1 | awk -F'"' '{print $2}')"
fi
JAVA_MAJOR="$(extract_java_major "$JAVA_VERSION_RAW")"
if ! [[ "$JAVA_MAJOR" =~ ^[0-9]+$ ]]; then
  echo "Error: Unable to detect Java version (got: \"$JAVA_VERSION_RAW\")." >&2
  exit 1
fi
if [ "$JAVA_MAJOR" -lt "$required_java_major" ]; then
  echo "Error: Java ${required_java_major}+ is required (detected: $JAVA_VERSION_RAW)." >&2
  echo "Install it (Debian/Ubuntu): sudo apt-get install -y openjdk-${required_java_major}-jdk" >&2
  echo "Then select it: sudo update-alternatives --config java" >&2
  exit 1
fi

MVN_JAVA_VERSION_RAW="$("$MVN" -version 2>/dev/null | awk -F': ' '/^Java version:/ {print $2; exit}' | cut -d',' -f1)"
if [ -z "$MVN_JAVA_VERSION_RAW" ]; then
  MVN_JAVA_VERSION_RAW="$JAVA_VERSION_RAW"
fi
MVN_JAVA_MAJOR="$(extract_java_major "$MVN_JAVA_VERSION_RAW")"
if ! [[ "$MVN_JAVA_MAJOR" =~ ^[0-9]+$ ]]; then
  echo "Error: Unable to detect the Java version used by Maven (got: \"$MVN_JAVA_VERSION_RAW\")." >&2
  exit 1
fi
if [ "$MVN_JAVA_MAJOR" -lt "$required_java_major" ]; then
  echo "Error: Maven is using Java $MVN_JAVA_VERSION_RAW, but this project requires Java ${required_java_major}+." >&2
  echo "Run: sudo update-alternatives --config java" >&2
  echo "If needed, also export JAVA_HOME to the JDK ${required_java_major} installation before running this script." >&2
  exit 1
fi

$MVN -DskipTests compile exec:java \
  -Dexec.mainClass=io.mcprpc.automesh.examples.BillingApiExampleMain
