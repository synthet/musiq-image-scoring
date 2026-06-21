#!/usr/bin/env bash
# Bridge WSL/Docker backend WebUI -> Cursor CLI (cursor-agent).
# - Docker (DOCKER_CONTAINER=1): cursor-agent on PATH inside the image.
# - WSL + run_webui.bat: forward to Windows-installed cursor-agent via cmd.exe.
# Point culling.agent_review.agent.command at this script and set provider "cursor".
# Auth: cursor-agent must be logged in on PATH for the WebUI process (no auth flag here).
# The adapter passes -p --output-format json <prompt>.
set -euo pipefail

if [[ -n "${DOCKER_CONTAINER:-}" ]]; then
  exec cursor-agent "$@"
fi

CMD="/mnt/c/Windows/System32/cmd.exe"
if [[ ! -f "$CMD" ]]; then
  echo "cursor_agent.sh: Windows cmd.exe not found at $CMD" >&2
  exit 127
fi

exec "$CMD" /c cursor-agent "$@"
