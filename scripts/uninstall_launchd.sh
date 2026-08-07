#!/usr/bin/env bash
set -euo pipefail

LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_FILE="${LAUNCH_AGENTS_DIR}/com.ai.email.agent.plist"
LABEL="com.ai.email.agent"

launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
launchctl disable "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true

if [[ -f "${PLIST_FILE}" ]]; then
  rm -f "${PLIST_FILE}"
fi

echo "Uninstalled launchd agent: ${LABEL}"
echo "To verify: launchctl print gui/$(id -u)/${LABEL} | cat"

