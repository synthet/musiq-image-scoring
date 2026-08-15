#!/usr/bin/env bash
# Bootstrap persistent research venv inside image-scoring-gpu-shell.
# Run: docker exec image-scoring-gpu-shell bash /app/scripts/docker_gpu_shell_bootstrap.sh
# Optional: INSTALL_STUDENT_SCORER=1 to pip-install requirements_student_scorer.txt
set -euo pipefail

VENV_DIR="${VENV_DIR:-/root/.venvs/research}"
APP_DIR="${APP_DIR:-/app}"

mkdir -p /root/.cache/huggingface /root/.cache/torch "$(dirname "$VENV_DIR")"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating venv at $VENV_DIR (system-site-packages: inherit image CUDA/app deps)..."
  python3 -m venv --system-site-packages "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip

# Persist extras on gpu_shell_home (/root) so they survive image rebuilds.
python -m pip install --user "ultralytics>=8.0.0"

if [[ "${INSTALL_STUDENT_SCORER:-0}" == "1" ]]; then
  echo "Installing student scorer extras..."
  python -m pip install -r "$APP_DIR/requirements/requirements_student_scorer.txt"
fi

echo "Bootstrap done."
echo "  source $VENV_DIR/bin/activate"
echo "  # Default image python also works for app deps (requirements_wsl_gpu)."
echo "  nvidia-smi"
echo "  python -c \"import torch; print(torch.cuda.is_available())\""
