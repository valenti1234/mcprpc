#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/release-all.sh <version> [--force] [--push]

Examples:
  ./scripts/release-all.sh 0.1.3
  ./scripts/release-all.sh v0.1.3 --force
  ./scripts/release-all.sh 0.1.3 --push

Behavior:
  - Updates versions in all packages
  - Commits with message "Release v<version>"
  - Creates annotated tags:
      v<version>
      mr-registry-v<version>
      mr-router-v<version>
      mc-gui-v<version>
      mc-automesh-v<version>
  - If --push is set, pushes main and the tags to origin
USAGE
}

if [[ $# -ge 1 ]]; then
  case "$1" in
    --help|-h) usage; exit 0 ;;
  esac
fi

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

VERSION_RAW="$1"
shift

FORCE="0"
DO_PUSH="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE="1"; shift ;;
    --push) DO_PUSH="1"; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

VERSION="${VERSION_RAW#v}"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid version: ${VERSION_RAW} (expected X.Y.Z or vX.Y.Z)" >&2
  exit 2
fi

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found in PATH" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git not found in PATH" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain=v1)" ]]; then
  echo "Working tree not clean. Commit/stash changes first." >&2
  exit 1
fi

update_pyproject_version() {
  local file="$1"
  local version="$2"
  python3 - "$file" "$version" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
version = sys.argv[2]

text = path.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)

out = []
in_project = False
updated = False

for line in lines:
  m = re.match(r'^\s*\[(.+?)\]\s*$', line.strip())
  if m:
    in_project = m.group(1) == "project"
    out.append(line)
    continue
  if in_project and re.match(r'^\s*version\s*=\s*".*"\s*$', line):
    indent = re.match(r'^(\s*)', line).group(1)
    out.append(f'{indent}version = "{version}"\n')
    updated = True
    continue
  out.append(line)

if not updated:
  raise SystemExit(f"Failed to update version in {path} (no [project].version found)")

path.write_text("".join(out), encoding="utf-8")
PY
}

update_package_json_version() {
  local file="$1"
  local version="$2"
  python3 - "$file" "$version" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
version = sys.argv[2]
data = json.loads(path.read_text(encoding="utf-8"))
data["version"] = version
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
}

update_pyproject_version "${ROOT_DIR}/mr-registry/pyproject.toml" "${VERSION}"
update_pyproject_version "${ROOT_DIR}/mr-router/pyproject.toml" "${VERSION}"
update_pyproject_version "${ROOT_DIR}/mc-gui/pyproject.toml" "${VERSION}"
update_pyproject_version "${ROOT_DIR}/mc-automesh/pyproject.toml" "${VERSION}"
update_package_json_version "${ROOT_DIR}/mc-node-automesh/package.json" "${VERSION}"

python3 -m compileall -q \
  "${ROOT_DIR}/mr-registry" \
  "${ROOT_DIR}/mr-router" \
  "${ROOT_DIR}/mc-gui" \
  "${ROOT_DIR}/mc-automesh" \
  "${ROOT_DIR}/mr-html"

git add -A
git commit -m "Release v${VERSION}"

tag_args=()
if [[ "${FORCE}" == "1" ]]; then
  tag_args+=("-f")
fi

git tag -a "${tag_args[@]}" "v${VERSION}" -m "v${VERSION}"
git tag -a "${tag_args[@]}" "mr-registry-v${VERSION}" -m "mr-registry v${VERSION}"
git tag -a "${tag_args[@]}" "mr-router-v${VERSION}" -m "mr-router v${VERSION}"
git tag -a "${tag_args[@]}" "mc-gui-v${VERSION}" -m "mc-gui v${VERSION}"
git tag -a "${tag_args[@]}" "mc-automesh-v${VERSION}" -m "mc-automesh v${VERSION}"

echo "Created commit and tags for v${VERSION}."
echo "Tags:"
git tag --list "*v${VERSION}" | sort

if [[ "${DO_PUSH}" == "1" ]]; then
  if ! git remote get-url origin >/dev/null 2>&1; then
    echo "No 'origin' remote configured; cannot push." >&2
    exit 1
  fi
  git push origin HEAD
  git push origin "v${VERSION}" \
    "mr-registry-v${VERSION}" \
    "mr-router-v${VERSION}" \
    "mc-gui-v${VERSION}" \
    "mc-automesh-v${VERSION}"
  echo "Pushed commit and tags to origin."
else
  echo "To push:"
  echo "  git push origin HEAD"
  echo "  git push origin v${VERSION} mr-registry-v${VERSION} mr-router-v${VERSION} mc-gui-v${VERSION} mc-automesh-v${VERSION}"
fi
