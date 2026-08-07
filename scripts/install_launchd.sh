#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEMPLATE_FILE="${PROJECT_DIR}/launchd/com.ai.email.agent.plist.template"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_FILE="${LAUNCH_AGENTS_DIR}/com.ai.email.agent.plist"
LOG_DIR="${PROJECT_DIR}/logs"
STDOUT_LOG="${LOG_DIR}/agent.stdout.log"
STDERR_LOG="${LOG_DIR}/agent.stderr.log"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"

if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
  echo "Missing .env in project root. Copy .env.example to .env and configure it first."
  exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Missing virtualenv Python at ${PYTHON_BIN}"
  echo "Create it with: python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

if [[ ! -f "${TEMPLATE_FILE}" ]]; then
  echo "Missing plist template: ${TEMPLATE_FILE}"
  exit 1
fi

mkdir -p "${LAUNCH_AGENTS_DIR}" "${LOG_DIR}"

sed \
  -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
  -e "s|__PYTHON_BIN__|${PYTHON_BIN}|g" \
  -e "s|__STDOUT_LOG__|${STDOUT_LOG}|g" \
  -e "s|__STDERR_LOG__|${STDERR_LOG}|g" \
  "${TEMPLATE_FILE}" > "${PLIST_FILE}"

launchctl bootout "gui/$(id -u)/com.ai.email.agent" >/dev/null 2>&1 || true
launchctl enable "gui/$(id -u)/com.ai.email.agent"
launchctl bootstrap "gui/$(id -u)" "${PLIST_FILE}"
launchctl kickstart -k "gui/$(id -u)/com.ai.email.agent"

echo "Installed and started launchd agent: com.ai.email.agent"
echo "Plist: ${PLIST_FILE}"
echo "Logs: ${STDOUT_LOG} / ${STDERR_LOG}"
echo "Status: launchctl print gui/$(id -u)/com.ai.email.agent | cat"
