#!/usr/bin/env bash
# Bridge WSL/Docker backend WebUI -> Gemini CLI.
# - Docker (DOCKER_CONTAINER=1): gemini on PATH inside the image.
# - WSL + run_webui.bat: forward to Windows npm global via cmd.exe.
# Point culling.agent_review.agent.command at this script (WSL: /mnt/d/.../gemini_agent.sh; Docker: /app/scripts/wsl/gemini_agent.sh).
set -euo pipefail

if [[ -n "${DOCKER_CONTAINER:-}" ]]; then
  exec gemini "$@"
fi

CMD="/mnt/c/Windows/System32/cmd.exe"
if [[ ! -f "$CMD" ]]; then
  echo "gemini_agent.sh: Windows cmd.exe not found at $CMD" >&2
  exit 127
fi

exec "$CMD" /c gemini "$@"
