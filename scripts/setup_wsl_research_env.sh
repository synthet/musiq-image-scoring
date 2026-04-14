#!/usr/bin/env bash
# Create WSL venv for research (all 3 models: SPAQ, AVA, LIQE).
# Run from project root in WSL: bash scripts/setup_wsl_research_env.sh
#
# Default location is the project-local .venv (same directory name as Windows native
# setup_windows_native.bat). Do not use one .venv for both Windows and WSL Python on
# the same clone — use separate clones, or VENV_DIR to point elsewhere.

set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"
VENV_DIR="${VENV_DIR:-$ROOT/.venv}"

echo "Project root: $ROOT"
echo "Venv directory: $VENV_DIR"

if [[ -d "$VENV_DIR" ]]; then
    echo "Venv already exists at $VENV_DIR. Activate with: source $VENV_DIR/bin/activate"
    exit 0
fi

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements/requirements_research.txt
echo "Installed. Verifying model load..."
python scripts/verify_research_models.py || true
echo "Done. Activate with: source $VENV_DIR/bin/activate"
echo "Then run: python scripts/research_models.py --test-size 50 --max-variants 20 --output-dir research_output"
