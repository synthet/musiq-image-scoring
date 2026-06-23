#!/usr/bin/env bash
# Resume library-wide re-cluster from checkpoint (WSL + ~/.venvs/tf).
#
#   bash scripts/research/clip_culling/resume_recluster.sh
#   DETACH=1 bash scripts/research/clip_culling/resume_recluster.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LOG="$REPO_ROOT/reports/clip-culling/rollout_recluster.log"
PY_SCRIPT="$SCRIPT_DIR/rollout_recluster.py"

PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$HOME/.venvs/tf/bin/python" ]]; then
    PYTHON_BIN="$HOME/.venvs/tf/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

run_job() {
  cd "$REPO_ROOT"
  source "$HOME/.venvs/tf/bin/activate"
  exec "$PYTHON_BIN" -u "$PY_SCRIPT"
}

mkdir -p "$(dirname "$LOG")"

if [[ "${DETACH:-0}" == "1" ]]; then
  setsid bash -c "cd '$REPO_ROOT' && source '$HOME/.venvs/tf/bin/activate' && '$PYTHON_BIN' -u '$PY_SCRIPT' >> '$LOG' 2>&1" < /dev/null &
  echo "launched detached; tail -f $LOG"
else
  run_job 2>&1 | tee -a "$LOG"
fi
