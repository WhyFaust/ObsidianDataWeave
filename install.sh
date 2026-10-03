#!/usr/bin/env bash
# Compatibility entrypoint; the stdlib Python installer owns all setup logic.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
    exec python3 "${REPO_DIR}/install.py" "$@"
elif command -v python >/dev/null 2>&1; then
    exec python "${REPO_DIR}/install.py" "$@"
else
    echo "ERROR: Python 3.10+ not found. Install Python and run install.py." >&2
    exit 1
fi
