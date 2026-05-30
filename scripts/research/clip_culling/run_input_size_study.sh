#!/usr/bin/env bash
# Run input-size study end-to-end (E2E DB @5433). Resumable: skips existing NPZ files.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
source "${HOME}/.venvs/tf/bin/activate"
export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 POSTGRES_DB=image_scoring_test
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:${ROOT}/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib"

LOG_DIR="$ROOT/reports/clip-culling/input-size"
mkdir -p "$LOG_DIR/npz"
MAIN_LOG="$LOG_DIR/study.log"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$MAIN_LOG"; }

log "=== input-size study start ==="
log "E2E: $POSTGRES_DB @ $POSTGRES_PORT"

python -m scripts.research.clip_culling.input_size_native 2>&1 | tee -a "$MAIN_LOG"

MODELS=(mobilenet clip_b32 openai openclip dinov2 siglip2)
EDGES="128,224,384,512,768"

for model in "${MODELS[@]}"; do
  for source in thumb file; do
    log "embed: model=$model source=$source"
    python -m scripts.research.clip_culling.input_size_embed \
      --track embedding \
      --models "$model" \
      --long-edges "$EDGES" \
      --source "$source" \
      --chunk 64 2>&1 | tee -a "$MAIN_LOG"
  done
done

log "iqa subset (500 images)"
python -m scripts.research.clip_culling.input_size_embed \
  --track iqa \
  --long-edges 224,384,512,768 \
  --source thumb \
  --subset 500 \
  --models liqe,topiq,arniqa 2>&1 | tee -a "$MAIN_LOG"

log "eval + report"
python -m scripts.research.clip_culling.input_size_eval --all 2>&1 | tee -a "$MAIN_LOG"
python -m scripts.research.clip_culling.report_input_size 2>&1 | tee -a "$MAIN_LOG"

log "=== input-size study complete ==="
