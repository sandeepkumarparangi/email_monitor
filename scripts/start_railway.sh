#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_DIR}"

export APP_RUNTIME_MODE="${APP_RUNTIME_MODE:-web}"
export BIND_HOST="${BIND_HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"

if [[ -n "${DATABASE_PATH:-}" ]]; then
  mkdir -p "$(dirname "${DATABASE_PATH}")"
fi

exec python -m app.main --mode "${APP_RUNTIME_MODE}"
