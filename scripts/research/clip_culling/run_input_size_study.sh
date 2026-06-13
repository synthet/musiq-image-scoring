#!/usr/bin/env bash
# Pipeline input-size study — resumable end-to-end (E2E DB @5433).
# Skips existing NPZ files. MobileNet omitted by default (TF GPU contention).
#
# Recommended detached launch (WSL):
#   setsid bash scripts/research/clip_culling/run_input_size_study.sh \
#     >> reports/clip-culling/input-size/study_nohup.log 2>&1 &
#
# Override models: MODELS=openclip,openai,dinov2,siglip2,clip_b32 bash ...
# Include MobileNet: MODELS=mobilenet,openclip,... bash ...
# Phase control: PHASE=1|2|3|all (default all)
set -euo pipefail

# Accept KEY=VALUE arguments as environment-style overrides so detached invocations
# like `setsid bash run_input_size_study.sh PHASE=1` behave as documented.
for arg in "$@"; do
  case "$arg" in
    PHASE=*|MODELS=*|EDGES=*|POSTGRES_HOST=*|POSTGRES_PORT=*|POSTGRES_DB=*)
      export "$arg"
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [PHASE=1|2|3|all|eval] [MODELS=a,b] [EDGES=128,224,...]" >&2
      exit 2
      ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
if [[ -f "${HOME}/.venvs/tf/bin/activate" ]]; then
  source "${HOME}/.venvs/tf/bin/activate"
else
  echo "Warning: ${HOME}/.venvs/tf/bin/activate not found; using current Python environment" >&2
fi
export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
export POSTGRES_PORT="${POSTGRES_PORT:-5433}"
export POSTGRES_DB="${POSTGRES_DB:-image_scoring_test}"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:${ROOT}/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib"

LOG_DIR="$ROOT/reports/clip-culling/input-size"
mkdir -p "$LOG_DIR/npz"
MAIN_LOG="$LOG_DIR/study.log"

# PyTorch culling towers first; omit mobilenet unless explicitly requested.
MODELS="${MODELS:-clip_b32,openai,openclip,dinov2,siglip2}"
EDGES="${EDGES:-128,224,384,512,768}"
PHASE="${PHASE:-all}"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$MAIN_LOG"; }

log "=== pipeline input-size study start (phase=$PHASE) ==="
log "E2E: $POSTGRES_DB @ $POSTGRES_PORT models=$MODELS"

python -m scripts.research.clip_culling.input_size_native 2>&1 | tee -a "$MAIN_LOG"

run_phase1() {
  IFS=',' read -ra MODEL_ARR <<< "$MODELS"
  IFS=',' read -ra EDGE_ARR <<< "$EDGES"
  for model in "${MODEL_ARR[@]}"; do
    for source in thumb file; do
      for le in "${EDGE_ARR[@]}"; do
        log "embed: model=$model source=$source long_edge=$le"
        python -m scripts.research.clip_culling.input_size_embed \
          --track embedding \
          --models "$model" \
          --long-edges "$le" \
          --source "$source" \
          --chunk 64 2>&1 | tee -a "$MAIN_LOG"
      done
    done
  done

  log "iqa subset (500 images): liqe, topiq, arniqa"
  python -m scripts.research.clip_culling.input_size_embed \
    --track iqa \
    --long-edges 224,384,512,768 \
    --source thumb \
    --subset 500 \
    --models liqe,topiq,arniqa 2>&1 | tee -a "$MAIN_LOG"
}

run_phase2() {
  log "iqa extended: topiq/arniqa @ 768,1024"
  python -m scripts.research.clip_culling.input_size_embed \
    --track iqa \
    --long-edges 768,1024 \
    --source thumb \
    --subset 500 \
    --models topiq,arniqa 2>&1 | tee -a "$MAIN_LOG"

  log "iqa MUSIQ: spaq, ava @ 224,384,512,768 (square pad)"
  python -m scripts.research.clip_culling.input_size_embed \
    --track iqa \
    --long-edges 224,384,512,768 \
    --source thumb \
    --subset 500 \
    --models spaq,ava 2>&1 | tee -a "$MAIN_LOG"
}

run_phase3() {
  log "tagging: keyword predictions from embedding NPZ"
  python -m scripts.research.clip_culling.input_size_tagging_eval \
    --sweep 2>&1 | tee -a "$MAIN_LOG"

  log "caption: BLIP @ 224,384,512,768"
  for source in thumb file; do
    for le in 224 384 512 768; do
      log "caption: source=$source long_edge=$le"
      python -m scripts.research.clip_culling.input_size_embed \
        --track caption \
        --long-edges "$le" \
        --source "$source" \
        --chunk 32 2>&1 | tee -a "$MAIN_LOG"
    done
  done
}

run_eval() {
  log "eval + report"
  python -m scripts.research.clip_culling.input_size_eval --all 2>&1 | tee -a "$MAIN_LOG"
  python -m scripts.research.clip_culling.report_input_size 2>&1 | tee -a "$MAIN_LOG"
}

case "$PHASE" in
  1) run_phase1; run_eval ;;
  2) run_phase2; run_eval ;;
  3) run_phase3; run_eval ;;
  all)
    run_phase1
    run_phase2
    run_phase3
    run_eval
    ;;
  eval) run_eval ;;
  *) log "Unknown PHASE=$PHASE (use 1|2|3|all|eval)"; exit 1 ;;
esac

log "=== pipeline input-size study complete (phase=$PHASE) ==="
