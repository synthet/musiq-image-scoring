# Python & Dependency Version Caveats

This project supports multiple runtime targets (Docker/WSL2 GPU, WSL research, and Windows-native CPU workflows).

To avoid stale docs and broken installs, treat requirement files as the canonical source of truth for package versions.

## Canonical requirements files by platform

- **WSL2 / Linux GPU (recommended for WebUI/dev):** `requirements/requirements_wsl_gpu.txt`
- **Windows-native CPU workflow (limited support):** `requirements.txt`
- **Minimal CPU-only experiments:** `requirements/requirements_simple.txt`

## Python compatibility caveat

`requirements.txt` currently uses a TensorFlow CPU constraint that is not compatible with Python 3.12.

If you are on Python 3.12, use the WSL/Linux path with `requirements/requirements_wsl_gpu.txt`.

## Documentation policy

- Do **not** hardcode package versions in setup docs unless absolutely necessary.
- Prefer referencing the platform's canonical requirements file.
- If a one-off pinned version must be documented, keep it synchronized with the relevant requirements file.
