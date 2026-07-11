#!/usr/bin/env bash
# One-shot launcher for full-library sub-stack backfill at threshold 0.04.
#   bash reports/clip-culling/run_backfill_sub_stacks_0.04.sh
#   DETACH=1 bash reports/clip-culling/run_backfill_sub_stacks_0.04.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG="$REPO_ROOT/reports/clip-culling/backfill_sub_stacks_0.04.log"
CKPT="reports/clip-culling/backfill_sub_stacks_0.04.checkpoint.json"
FB_LIB="$REPO_ROOT/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib"

run_job() {
  cd "$REPO_ROOT"
  export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:$FB_LIB"
  source "$HOME/.venvs/tf/bin/activate"
  exec python -u -m scripts.maintenance.backfill_sub_stacks \
    --resume \
    --checkpoint "$CKPT"
}

mkdir -p "$(dirname "$LOG")"

if [[ "${DETACH:-0}" == "1" ]]; then
  setsid bash -c "
    export LD_LIBRARY_PATH=\"\${LD_LIBRARY_PATH:-}:$FB_LIB\"
    cd '$REPO_ROOT'
    source '$HOME/.venvs/tf/bin/activate'
    exec python -u -m scripts.maintenance.backfill_sub_stacks --resume --checkpoint '$CKPT'
  " >> "$LOG" 2>&1 < /dev/null &
  echo "launched detached; tail -f $LOG"
else
  run_job 2>&1 | tee -a "$LOG"
fi
