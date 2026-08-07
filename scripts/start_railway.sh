#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_DIR}"

export APP_RUNTIME_MODE="${APP_RUNTIME_MODE:-web}"
export BIND_HOST="${BIND_HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"
credentials_file="${GOOGLE_CREDENTIALS_FILE:-credentials.json}"
token_file="${GOOGLE_TOKEN_FILE:-token.json}"

if [[ -n "${GOOGLE_CREDENTIALS_JSON_B64:-}" ]]; then
  mkdir -p "$(dirname "${credentials_file}")"
  printf '%s' "${GOOGLE_CREDENTIALS_JSON_B64}" | base64 -d > "${credentials_file}"
elif [[ -n "${GOOGLE_CREDENTIALS_JSON:-}" ]]; then
  mkdir -p "$(dirname "${credentials_file}")"
  printf '%s' "${GOOGLE_CREDENTIALS_JSON}" > "${credentials_file}"
fi

if [[ -n "${GOOGLE_TOKEN_JSON_B64:-}" ]]; then
  mkdir -p "$(dirname "${token_file}")"
  printf '%s' "${GOOGLE_TOKEN_JSON_B64}" | base64 -d > "${token_file}"
elif [[ -n "${GOOGLE_TOKEN_JSON:-}" ]]; then
  mkdir -p "$(dirname "${token_file}")"
  printf '%s' "${GOOGLE_TOKEN_JSON}" > "${token_file}"
fi

if [[ -n "${DATABASE_PATH:-}" ]]; then
  mkdir -p "$(dirname "${DATABASE_PATH}")"
fi

exec python -m app.main --mode "${APP_RUNTIME_MODE}"
