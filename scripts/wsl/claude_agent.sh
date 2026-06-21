#!/usr/bin/env bash
# Bridge WSL/Docker backend WebUI -> Claude Code CLI.
# - Docker (DOCKER_CONTAINER=1): claude on PATH inside the image.
# - WSL + run_webui.bat: forward to Windows-installed claude via cmd.exe.
# Point culling.agent_review.agent.command at this script and set provider "claude".
# Auth: claude must be logged in on PATH for the WebUI process (no auth flag here).
# The adapter passes -p --output-format json --dangerously-skip-permissions <prompt>.
set -euo pipefail

if [[ -n "${DOCKER_CONTAINER:-}" ]]; then
  exec claude "$@"
fi

CMD="/mnt/c/Windows/System32/cmd.exe"
if [[ ! -f "$CMD" ]]; then
  echo "claude_agent.sh: Windows cmd.exe not found at $CMD" >&2
  exit 127
fi

exec "$CMD" /c claude "$@"
