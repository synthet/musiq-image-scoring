#!/usr/bin/env bash
# Bridge WSL/Docker backend WebUI -> Antigravity CLI (agy).
# - Docker (DOCKER_CONTAINER=1): agy on PATH (/root/.local/bin from image install).
# - WSL + run_webui.bat: forward to Windows agy via cmd.exe (install.ps1 from antigravity.google).
# Point culling.agent_review.agent.command at this script and provider "antigravity".
set -euo pipefail

if [[ -x /root/.local/bin/agy ]]; then
  AGY_BIN=/root/.local/bin/agy
else
  AGY_BIN="${AGY_BIN:-agy}"
fi

run_prompt() {
  local prompt="$1"
  # Non-TTY subprocess capture can drop stdout on some agy builds; PTY wrapper is the Linux fallback.
  if command -v script >/dev/null 2>&1 && [[ "${AGY_USE_PTY:-1}" != "0" ]]; then
    export AGY_CULL_PROMPT="$prompt"
    script -qec "$AGY_BIN -p \"\$AGY_CULL_PROMPT\" --dangerously-skip-permissions" /dev/null
    return $?
  fi
  "$AGY_BIN" -p "$prompt" --dangerously-skip-permissions
}

# Single non-flag argument = agent cull review prompt from cli_adapter.
if [[ $# -eq 1 && "$1" != -* ]]; then
  run_prompt "$1"
  exit $?
fi

if [[ -n "${DOCKER_CONTAINER:-}" ]]; then
  exec "$AGY_BIN" "$@"
fi

CMD="/mnt/c/Windows/System32/cmd.exe"
if [[ ! -f "$CMD" ]]; then
  echo "antigravity_agent.sh: Windows cmd.exe not found at $CMD" >&2
  exit 127
fi

exec "$CMD" /c agy "$@"
