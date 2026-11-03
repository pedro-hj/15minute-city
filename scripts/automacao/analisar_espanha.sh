#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v uv >/dev/null 2>&1; then
    echo "ERRO: uv não encontrado no PATH." >&2
    exit 1
fi
exec uv run --no-project --with psutil==7.2.2 python -u "$SCRIPT_DIR/lote.py" --country ES "$@"
