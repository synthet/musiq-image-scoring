#!/usr/bin/env bash
set -euo pipefail

# Run pytest tests marked as `wsl`.
#
# IMPORTANT: Default venv location is inside the WSL filesystem (ext4) for speed.
#
# Usage:
#   bash ./scripts/wsl/run_wsl_tests.sh
#
# Optional env vars:
#   VENV_DIR=~/.venvs/image-scoring-tests
#   PYTEST_MARK_EXPR='wsl and not network'
#   PYTEST_ARGS='-k "not slow"'
#   IMAGE_SCORING_TEST_RAW_FILE=/mnt/d/Photos/.../DSC_0001.NEF
#   IMAGE_SCORING_TEST_THUMBNAIL=/path/to/image-scoring/thumbnails/....
#   IMAGE_SCORING_RUN_NETWORK_TESTS=1
#   IMAGE_SCORING_RUN_KAGGLE_DOWNLOADS=1

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

VENV_DIR="${VENV_DIR:-$HOME/.venvs/image-scoring-tests}"
PYTEST_MARK_EXPR="${PYTEST_MARK_EXPR:-wsl and not network}"
PYTEST_ARGS="${PYTEST_ARGS:-}"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[error] venv not found at $VENV_DIR. Run: bash ./scripts/wsl/setup_wsl_test_env.sh" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

echo "[run] pytest -ra -m \"$PYTEST_MARK_EXPR\" $PYTEST_ARGS"
python -m pytest -ra -m "$PYTEST_MARK_EXPR" $PYTEST_ARGS
