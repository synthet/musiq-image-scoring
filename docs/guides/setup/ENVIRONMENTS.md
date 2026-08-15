---
type: Guide
title: Virtual Environments
description: Python venvs for WebUI, WSL tests, and optional Windows/research; gpu-shell is the default script runner.
resource: guides/setup/ENVIRONMENTS.md
tags: [venv, wsl, python, setup, docker]
timestamp: 2026-08-14T21:10:00Z
okf_version: 0.1
---

# Virtual Environments and Script Usage

This document describes each Python environment referenced in the image-scoring project: where they live, what uses them, and which one the Web UI uses by default.

**Host topology** (Ubuntu WSL vs `docker-desktop` vs Windows; Docker WebUI + **gpu-shell**): [wsl-vs-docker-topology.md](wsl-vs-docker-topology.md). You can run **Compose Postgres + `image-scoring-webui` + `gpu-shell`** without Ubuntu; the WSL/Windows venvs below apply when you use host Python instead.

## Summary

| Environment | Location | Purpose | Used by |
|-------------|----------|---------|---------|
| **Web UI / app (WSL, optional)** | `~/.venvs/tf` (WSL) | Host Python when Ubuntu is installed | `run_webui.bat` only |
| **Web UI (Docker)** | Inside `image-scoring-webui` image | Same app stack in Compose | `docker compose up webui` — see [DOCKER_SETUP.md](DOCKER_SETUP.md) |
| **GPU shell (Docker)** | `image-scoring-gpu-shell` (+ optional `/root/.venvs/research`) | Scripts / research / CUDA without Ubuntu | `scripts\batch\docker_gpu_run.bat`, `Invoke-GpuShell.ps1`, `docker_gpu_shell.bat` |
| **Tests** | `~/.venvs/image-scoring-tests` (WSL) | Pytest WSL-marked tests | `run_wsl_tests.sh`, `Run-WSLTests.ps1` |
| **Project local (optional)** | `.venv` (project root) | Windows WebUI + CLI (CPU, no VILA); or WSL research env (SPAQ/AVA/LIQE) | `run_webui_windows.bat`, `scripts/setup_wsl_research_env.sh` |

**Default for scripts / `modules.*` / ML:** Compose **`image-scoring-gpu-shell`**. **Default for the Web UI:** `image-scoring-webui`. Ubuntu `~/.venvs/tf` is optional (`run_webui.bat`).

**Project-local venv:** The only conventional directory name at the repo root is **`.venv`** (gitignored). It is optional and used for Windows-native workflows and/or WSL research (see **section 3** below). It is excluded from pytest collection (`pytest.ini`).

---

## 1. `~/.venvs/tf` (WSL) — Web UI and app scripts

- **Purpose:** Optional Ubuntu host env for `run_webui.bat` when not using Docker WebUI.
- **Used by:**
  - **`run_webui.bat`** — activates this venv in WSL and runs `python launch.py` (which then runs `webui.py`).
- **Setup:** See [WSL2 TensorFlow GPU Setup](WSL2_TENSORFLOW_GPU_SETUP.md) and [WSL Python Packages](WSL_PYTHON_PACKAGES.md). Typically:
  ```bash
  python3 -m venv ~/.venvs/tf
  source ~/.venvs/tf/bin/activate
  pip install -r requirements/requirements_wsl_gpu.txt  # canonical WSL/Linux GPU requirements
  ```
- **Note:** The path is in the **WSL home directory** (`~`), not under the project. Project-local `.venv` is not used by `run_webui.bat` or these scripts.

---

## 2. `~/.venvs/image-scoring-tests` (WSL) — Pytest WSL tests

- **Purpose:** Dedicated venv for running pytest tests marked with `wsl` (WSL/Linux). Kept on the WSL filesystem for speed and stability.
- **Used by:**
  - **`scripts/wsl/run_wsl_tests.sh`** — activates this venv and runs pytest (default: `-ra -m wsl`).
  - **`scripts/wsl/setup_wsl_test_env.sh`** — creates this venv and installs test/ML deps.
  - **`scripts/powershell/Run-WSLTests.ps1`** — invokes the WSL test script; default `$VenvDir` is `~/.venvs/image-scoring-tests`.
- **Override:** Set `VENV_DIR` (e.g. `VENV_DIR=~/.venvs/image-scoring-tests`) when calling the shell scripts; use `-VenvDir` in the PowerShell script.
- **Docs:** [WSL Tests](../testing/WSL_TESTS.md), [Test Status](../testing/TEST_STATUS.md).

---

## 3. `.venv` (project root — optional local)

There is **one** conventional name for a virtual environment in the repository: **`.venv`** at the project root (gitignored). It is **not** used by `run_webui.bat` (which uses `~/.venvs/tf`). Use it only when you want a project-local venv instead of or in addition to the home-directory WSL envs above.

### Windows native

- **Purpose:** **Windows-native** Python for WebUI and CLI (CPU-only, no VILA, no GPU). Documented as "Option 3" / "Option 3b" in the main README.
- **Used by:** **`run_webui_windows.bat`** — activates `.venv` and runs `python launch.py` → `webui.py`. You can activate it manually for CLI use.
- **Setup:** `scripts\setup\setup_windows_native.bat` creates `.venv` and installs dependencies.
- **Limitations:** CPU-only, no VILA; not the same stack as `run_webui.bat` (WSL + `~/.venvs/tf`).

### WSL — research stack (optional)

- **Purpose:** SPAQ / AVA / LIQE research tooling (`requirements/requirements_research.txt`).
- **Used by:** **`scripts/setup_wsl_research_env.sh`** — creates or uses **`$ROOT/.venv`** in WSL (override with `VENV_DIR=...`).
- **Important:** A `.venv` created with **Windows** `python -m venv` and one created with **WSL** `python3 -m venv` are **not interchangeable** if they share the same path on a `/mnt/...` drive — binaries and layout differ. Use **either** Windows `.venv` **or** WSL `.venv` on a given clone for local work, or keep research in a separate clone. Do not alternate without removing and recreating `.venv`.

---

## What `run_webui.bat` does

1. Converts the project root to a WSL path (e.g. `D:\path\to\repo` → `/mnt/d/path/to/repo`; adjust the drive letter for your setup).
2. Sets `LD_LIBRARY_PATH` to include the Firebird Linux lib path under the project.
3. Sets `ENABLE_MCP_SERVER` (default `1`) for optional MCP.
4. Runs in WSL: **`source ~/.venvs/tf/bin/activate && python launch.py %*`**.
5. `launch.py` checks/installs minimal UI deps (e.g. gradio, pydantic), ensures Firebird is running, then runs **`webui.py`** with the same Python (from `~/.venvs/tf`).

So the **default environment for the Web UI is `~/.venvs/tf` in WSL**. No project-local `.venv` is used by this path.

---

## Running scripts in the same environment as the Web UI

For any script that uses `modules`, the database, or config (e.g. under `scripts/`), use the **same** WSL environment as the Web UI:

- **From WSL** (recommended):
  ```bash
  cd /path/to/image-scoring-backend   # use your WSL path to the repo
  export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib
  source ~/.venvs/tf/bin/activate
  python scripts/path/to/script.py
  ```
- **From Windows:** Use the existing batch/PowerShell wrappers (they already invoke WSL with `~/.venvs/tf`), or run the same commands via `wsl -e bash -c "..."` as in `run_webui.bat` / `run_analysis.bat`.

See also the Cursor rule **Run Python in WSL (Webapp Environment)** (`.cursor/rules/python-wsl-webapp-env.mdc`), which enforces using this environment for dependency-using scripts.

---

## Quick reference

| Question | Answer |
|----------|--------|
| What does the Web UI use (WSL path)? | WSL + **`~/.venvs/tf`** (via `run_webui.bat`). |
| What does the Web UI use (Docker path)? | `image-scoring-webui` container — [DOCKER_SETUP.md](DOCKER_SETUP.md), [topology](wsl-vs-docker-topology.md). |
| Scripts / research without Ubuntu? | Compose **`gpu-shell`** — [DOCKER_SETUP.md § GPU shell](DOCKER_SETUP.md#gpu-shell-scripts--research). |
| Does default Web UI (`run_webui.bat`) use project `.venv`? | No — it uses `~/.venvs/tf`. |
| Where do WSL pytest tests run? | In **`~/.venvs/image-scoring-tests`** (or custom `VENV_DIR`). |


See also: [Python & Dependency Version Caveats](PYTHON_VERSION_CAVEATS.md), [WSL vs Docker topology](wsl-vs-docker-topology.md).
