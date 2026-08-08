#!/usr/bin/env bash
# Bird-bbox crop study — phased, resumable orchestrator.
#
# Measures what a subject-localized crop buys each pipeline phase versus the whole
# downscaled frame. Reads production READ-ONLY; every artifact lands under
# reports/bird-crop/ or reports/clip-culling/input-size/npz/.
#
# Recommended detached launch (WSL):
#   setsid bash scripts/research/bird_crop/run_bird_crop_study.sh \
#     >> reports/bird-crop/study_nohup.log 2>&1 &
#
# Phases:
#   0     label-set template + contact sheets (no GPU; then YOU fill in verdicts)
#   1     zero-inference geometry study (no GPU)
#   2     crop-vs-full sweep: embedding, iqa, caption tracks (GPU)
#   2b    synthetic degradation sensitivity (GPU)
#   3     BioCLIP species crop vs whole image (GPU)
#   4     classical focus measures + camera AF intent (no GPU)
#   report consolidate everything into reports/bird-crop/REPORT.md
#   free   phases needing no GPU (0 + 1)
#   all    everything
#
# The GPU phases (2, 2b, 3) all read one pinned list of image ids so that every
# track measures the same population. There is deliberately no folder or subset
# override for them: strided sampling of the currently-boxed rows is what made the
# first sweep's runs mutually incomparable (see
# reports/clip-culling/input-size/npz/archive_mixed_population/README.md).
#
# Overrides (KEY=VALUE args, allowlisted):
#   PHASE=free|0|1|2|2b|3|4|report|all (default: free)
#   IDS_FILE=path/to/ids.txt           pinned population for phases 2/2b/3
#   SOURCES=file,crop,croppad25        crop variants to sweep in phase 2
#   EDGES=224,384,512                  long edges for phase 2
#   MODELS=clip_b32,openclip_l14       embedding models for phase 2
#   VENV_PATH=/path/to/venv            default ~/.venvs/tf
set -euo pipefail

usage() {
  cat >&2 <<EOF
Usage: $0 [PHASE=free|0|1|2|2b|3|4|report|all] [IDS_FILE=path] [SOURCES=a,b]
          [EDGES=224,384] [MODELS=a,b] [VENV_PATH=/path/to/venv]
EOF
}

for arg in "$@"; do
  if [[ "$arg" == "-h" || "$arg" == "--help" ]]; then
    usage
    exit 0
  fi
  key="${arg%%=*}"
  value="${arg#*=}"
  if [[ "$key" == "$arg" ]]; then
    echo "Unknown argument: $arg" >&2
    usage
    exit 2
  fi
  case "$key" in
    PHASE|IDS_FILE|SOURCES|EDGES|MODELS|VENV_PATH)
      export "$key=$value"
      ;;
    *)
      echo "Unknown override: $key" >&2
      usage
      exit 2
      ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

LOG_DIR="$ROOT/reports/bird-crop"
mkdir -p "$LOG_DIR"
MAIN_LOG="$LOG_DIR/study.log"

PHASE="${PHASE:-free}"
case "$PHASE" in
  free|0|1|2|2b|3|4|report|all) ;;
  *) echo "Unknown PHASE=$PHASE (use free|0|1|2|2b|3|4|report|all)" >&2; exit 2 ;;
esac

# The pinned study population. Generated from the human label set by
# scripts/research/bird_crop/pin_study_set.py, so the within-burst verdicts apply
# to every track that reads it.
IDS_FILE="${IDS_FILE:-reports/bird-crop/study_image_ids.txt}"
# cropctx is omitted on purpose: measured on this library it expands only 5 of
# ~25k boxes at 224px, because 45MP frames already give native boxes far larger
# than the model input. It stays available for long edges >= 768.
SOURCES="${SOURCES:-file,crop,croppad25,croppad50}"
EDGES="${EDGES:-224,384,512}"
# Must match keys in input_size_embed.EMBEDDING_MODELS / embed_persist.TOWERS.
# openclip = ViT-L-14/laion2b (plan's "openclip_l14"); openai = ViT-L-14/openai.
# BioCLIP species is Phase 3 (species_crop_eval), not this embedding track.
MODELS="${MODELS:-clip_b32,openclip,openai}"

# Fail before the venv and the models load: a missing pin means hours of GPU time
# would produce another population that cannot be compared with anything.
case "$PHASE" in
  2|2b|3|4|all)
    if [[ ! -f "$ROOT/$IDS_FILE" && ! -f "$IDS_FILE" ]]; then
      echo "Pinned id list not found: $IDS_FILE" >&2
      echo "Generate it with:" >&2
      echo "  python -m scripts.research.bird_crop.pin_study_set" >&2
      exit 2
    fi
    ;;
esac

VENV_PATH="${VENV_PATH:-${HOME}/.venvs/tf}"
if [[ ! -f "${VENV_PATH}/bin/activate" ]]; then
  echo "Virtualenv not found: ${VENV_PATH}/bin/activate" >&2
  echo "Set VENV_PATH=/path/to/venv or create ${HOME}/.venvs/tf." >&2
  exit 2
fi
# shellcheck disable=SC1091
source "${VENV_PATH}/bin/activate"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$MAIN_LOG"; }

log "=== bird-crop study start (phase=$PHASE) ==="
log "sources=$SOURCES edges=$EDGES models=$MODELS"
if [[ -f "$IDS_FILE" ]]; then
  log "ids_file=$IDS_FILE ($(grep -c '^[0-9]' "$IDS_FILE" || true) pinned id(s))"
fi

run_phase0() {
  log "phase 0: label-set template + contact sheets"
  python -m scripts.research.bird_crop.build_label_set 2>&1 | tee -a "$MAIN_LOG"
  log "phase 0 done — fill in the 'verdict' column in reports/bird-crop/labels/label_set.csv"
}

run_phase1() {
  log "phase 1: zero-inference geometry study"
  python -m scripts.research.bird_crop.geometry_eval 2>&1 | tee -a "$MAIN_LOG"
}

run_phase2() {
  # --image-ids-file pins every run to the same images and implies --boxed-only,
  # so the crop and full-frame arms cannot drift apart the way they did in the
  # first sweep. It is mutually exclusive with --subset, which is why no image cap
  # appears here: the pinned list *is* the population.
  log "phase 2a: embedding track"
  python -m scripts.research.clip_culling.input_size_embed \
    --track embedding --models "$MODELS" --long-edges "$EDGES" \
    --source "$SOURCES" \
    --from-prod --image-ids-file "$IDS_FILE" 2>&1 | tee -a "$MAIN_LOG"

  log "phase 2b: iqa track (one source per run — the sweep takes a single source)"
  IFS=',' read -ra SRC_ARR <<< "$SOURCES"
  for src in "${SRC_ARR[@]}"; do
    log "  iqa source=$src"
    python -m scripts.research.clip_culling.input_size_embed \
      --track iqa --models liqe,topiq,arniqa --long-edges "$EDGES" \
      --source "$src" \
      --from-prod --image-ids-file "$IDS_FILE" 2>&1 | tee -a "$MAIN_LOG"
  done

  log "phase 2c: caption track (BLIP)"
  python -m scripts.research.clip_culling.input_size_embed \
    --track caption --long-edges "$EDGES" \
    --source "$SOURCES" \
    --from-prod --image-ids-file "$IDS_FILE" 2>&1 | tee -a "$MAIN_LOG"

  # The eval reads image metadata and capture times from the database, and its
  # defaults belong to the E2E culling spike: E2E db/port and folder scope
  # 62,44,45,676, which has *zero* overlap with the pinned population. Left alone
  # it joins production NPZ ids against the wrong database and finds nothing, so
  # production and the pin's own folder scope are both passed explicitly. Scope is
  # by folder, not by id, because burst grouping needs a pinned image's
  # neighbouring frames to see the burst it belongs to.
  log "phase 2 eval"
  local eval_folders
  eval_folders="$(python -m scripts.research.bird_crop.pin_study_set \
    --print-folders --ids-file "$IDS_FILE")"
  log "  eval folder scope: $eval_folders"
  CLIP_CULLING_FOLDERS="$eval_folders" \
  POSTGRES_DB=image_scoring POSTGRES_PORT=5432 \
    python -m scripts.research.clip_culling.input_size_eval \
      --all --from-prod 2>&1 | tee -a "$MAIN_LOG"
}

run_phase2b() {
  log "phase 2b: synthetic degradation sensitivity"
  python -m scripts.research.bird_crop.degradation_eval \
    --models liqe,topiq,arniqa --image-ids-file "$IDS_FILE" 2>&1 | tee -a "$MAIN_LOG"
}

run_phase3() {
  log "phase 3: species coverage + crop vs whole image"
  python -m scripts.research.bird_crop.species_crop_eval \
    --image-ids-file "$IDS_FILE" 2>&1 | tee -a "$MAIN_LOG"
}

run_phase4() {
  log "phase 4: classical focus measures + camera AF intent"
  python -m scripts.research.bird_crop.focus_eval     --image-ids-file "$IDS_FILE" 2>&1 | tee -a "$MAIN_LOG"
}

run_report() {
  log "consolidating report"
  python -m scripts.research.bird_crop.report 2>&1 | tee -a "$MAIN_LOG"
}

case "$PHASE" in
  free)   run_phase0; run_phase1; run_report ;;
  0)      run_phase0 ;;
  1)      run_phase1; run_report ;;
  2)      run_phase2; run_report ;;
  2b)     run_phase2b; run_report ;;
  3)      run_phase3; run_report ;;
  4)      run_phase4; run_report ;;
  report) run_report ;;
  all)
    run_phase0
    run_phase1
    run_phase2
    run_phase2b
    run_phase3
    run_phase4
    run_report
    ;;
esac

log "=== bird-crop study complete (phase=$PHASE) ==="
