#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${KAREN_INSTALL_PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "需要 Python 3.10+；请先安装 python3" >&2
    exit 1
fi
exec "$PYTHON" "$ROOT/karen_install.py" "$@"
