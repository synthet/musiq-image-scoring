#!/usr/bin/env bash
# Bridge WSL backend WebUI -> Windows Gemini CLI (npm global on the Windows host).
# Point culling.agent_review.agent.command at this script when run_webui.bat is used.
set -euo pipefail

CMD="/mnt/c/Windows/System32/cmd.exe"
if [[ ! -f "$CMD" ]]; then
  echo "gemini_agent.sh: Windows cmd.exe not found at $CMD" >&2
  exit 127
fi

exec "$CMD" /c gemini "$@"
