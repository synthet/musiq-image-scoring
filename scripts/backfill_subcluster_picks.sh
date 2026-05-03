#!/usr/bin/env bash
# Wrapper around scripts/backfill_subcluster_picks.py.
#
# Defaults to a safe dry-run with verbose logging so you can sanity-check
# the impact before any DB writes. Pass --live (or set LIVE=1) to actually
# persist decisions.
#
# Usage examples:
#   bash scripts/backfill_subcluster_picks.sh                     # dry-run, all stacks
#   bash scripts/backfill_subcluster_picks.sh --folder /mnt/d/Photos/2024
#   LIVE=1 bash scripts/backfill_subcluster_picks.sh              # persist
#   bash scripts/backfill_subcluster_picks.sh --live --write-sidecars
#   THRESHOLD=0.04 bash scripts/backfill_subcluster_picks.sh --live
#
# Environment overrides (all optional):
#   PYTHON           — interpreter (default: ~/.venvs/tf/bin/python if present, else python3)
#   THRESHOLD        — cosine distance threshold (overrides config)
#   PICK_FRACTION    — pick/reject band fraction (default: 0.33)
#   SCORE_FIELD      — sort column (default: score_general)
#   LIMIT            — process at most N stacks (0 = unlimited)
#   FOLDER           — restrict to a folder subtree
#   LIVE             — set to 1 to disable dry-run
#   WRITE_SIDECARS   — set to 1 to also rewrite XMP sidecars
#   LD_LIBRARY_PATH  — preserved if already set (Firebird FFI)
#
# Any extra argv tokens are forwarded verbatim to the Python script, so you
# can also write `bash backfill_subcluster_picks.sh --threshold 0.04 --live`.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PY_SCRIPT="$SCRIPT_DIR/backfill_subcluster_picks.py"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,30p' "$0"
  exit 0
fi

# ---- Pick a Python interpreter ----------------------------------------------
# Project memory (CLAUDE.md, AGENTS.md) standardises on ~/.venvs/tf for any
# code that imports modules.* on WSL. Fall back to python3 elsewhere so the
# script also runs on plain Windows (Git Bash) or CI containers.
PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$HOME/.venvs/tf/bin/python" ]]; then
    PYTHON_BIN="$HOME/.venvs/tf/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "backfill_subcluster_picks.sh: no python interpreter found" >&2
    exit 1
  fi
fi

# ---- Build CLI args ---------------------------------------------------------
ARGS=()

# Forward env-var overrides as flags (only when set & non-empty).
[[ -n "${THRESHOLD:-}" ]]      && ARGS+=("--threshold" "$THRESHOLD")
[[ -n "${PICK_FRACTION:-}" ]]  && ARGS+=("--pick-fraction" "$PICK_FRACTION")
[[ -n "${SCORE_FIELD:-}" ]]    && ARGS+=("--score-field" "$SCORE_FIELD")
[[ -n "${LIMIT:-}" ]]          && ARGS+=("--limit" "$LIMIT")
[[ -n "${FOLDER:-}" ]]         && ARGS+=("--folder" "$FOLDER")
[[ "${WRITE_SIDECARS:-0}" == "1" ]] && ARGS+=("--write-sidecars")

# Default to dry-run + verbose unless caller opts into live mode.
WANT_LIVE="${LIVE:-0}"
WANT_DRY=1
WANT_VERBOSE=1

# Scan passthrough args for --live / --dry-run / --verbose so callers can mix
# both forms (env var or flag).
PASSTHROUGH=()
for arg in "$@"; do
  case "$arg" in
    --live)    WANT_LIVE=1 ;;
    --dry-run) WANT_LIVE=0 ;;
    --quiet)   WANT_VERBOSE=0 ;;
    *)         PASSTHROUGH+=("$arg") ;;
  esac
done

if [[ "$WANT_LIVE" == "1" ]]; then
  WANT_DRY=0
fi

if [[ "$WANT_DRY" == "1" ]]; then
  ARGS+=("--dry-run")
fi
if [[ "$WANT_VERBOSE" == "1" ]]; then
  ARGS+=("--verbose")
fi

# Always forward unknown tokens last so they override our defaults if needed.
if [[ ${#PASSTHROUGH[@]} -gt 0 ]]; then
  ARGS+=("${PASSTHROUGH[@]}")
fi

# ---- Banner -----------------------------------------------------------------
MODE="DRY-RUN (no DB writes)"
if [[ "$WANT_DRY" == "0" ]]; then
  MODE="LIVE — will rewrite IMAGES.cull_decision"
fi

echo "================================================================"
echo " sub-cluster pick/reject backfill"
echo "  mode:   $MODE"
echo "  python: $PYTHON_BIN"
echo "  repo:   $REPO_ROOT"
[[ -n "${THRESHOLD:-}" ]]     && echo "  threshold: $THRESHOLD"
[[ -n "${FOLDER:-}" ]]        && echo "  folder:    $FOLDER"
[[ -n "${LIMIT:-}" ]]         && echo "  limit:     $LIMIT"
[[ "${WRITE_SIDECARS:-0}" == "1" ]] && echo "  sidecars:  enabled"
echo "================================================================"

cd "$REPO_ROOT"
exec "$PYTHON_BIN" "$PY_SCRIPT" "${ARGS[@]}"
