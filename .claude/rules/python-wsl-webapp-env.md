---
description: Which Python environment to use for app, scripts, and tests; run dependency-using scripts in image-scoring-gpu-shell
alwaysApply: true
---

# Python Environments — When to Use What

Use the environment that matches what you are running. **Default for scripts / `modules.*` / ML: Compose `gpu-shell` (`image-scoring-gpu-shell`).** Ubuntu WSL `~/.venvs/tf` is optional.

## Quick decision

| What you're doing | Environment | How to run |
|-------------------|-------------|------------|
| **Web UI** | `image-scoring-webui` | `docker compose up -d db webui` (already the day-to-day path) |
| **Web UI (Ubuntu WSL, optional)** | `~/.venvs/tf` (WSL) | `run_webui.bat` — only if Ubuntu is installed |
| **Web UI (Windows native)** | `.venv` (project root) | `run_webui_windows.bat` |
| **Any script that uses `modules`, DB, config, or ML** (e.g. `scripts/`, backfills) | **`image-scoring-gpu-shell`** | `scripts\batch\docker_gpu_run.bat <script> [args]` or `.\scripts\powershell\Invoke-GpuShell.ps1 python <script> [args]` |
| **Pytest tests marked `wsl`** | `~/.venvs/image-scoring-tests` (Ubuntu WSL) | `scripts/wsl/run_wsl_tests.sh` or `Run-WSLTests.ps1` — skip if Ubuntu is not registered |
| **Windows-native, CPU-only** (no GPU, no VILA) | `.venv` (project root) | Optional. No script in the repo uses this by default. |

When in doubt (e.g. running a script under `scripts/` that imports `modules` or touches the DB): use **gpu-shell**, not Windows Python and not Ubuntu WSL.

---

# Run Python in gpu-shell

When running Python scripts that use project dependencies (`modules.*`, database, config, ML), **run them in `image-scoring-gpu-shell`**.

## Start once

```powershell
docker compose --profile gpu-shell up -d db gpu-shell
# or: scripts\batch\docker_gpu_shell.bat   (interactive bash)
```

## How to run scripts

**From Windows (PowerShell/CMD)** — canonical:

```powershell
scripts\batch\docker_gpu_run.bat scripts/doctor.py --no-gpu
scripts\batch\docker_gpu_run.bat scripts/backfill_bird_bbox.py --all-null
.\scripts\powershell\Invoke-GpuShell.ps1 python scripts/doctor.py --no-gpu
.\scripts\powershell\Invoke-GpuShell.ps1 -Detach python scripts/backfill_bird_bbox.py --all-null
```

**Inside the container:**

```bash
docker exec -i -w /app -e PYTHONPATH=/app image-scoring-gpu-shell python scripts/doctor.py --no-gpu
```

Repo is mounted at `/app`. Photo library bind is `PHOTOS_BIND_SOURCE` → `/mnt/d/Photos` (set in `.env` on Docker Desktop for Windows). Persistent caches: `gpu_shell_home` (`/root`), `hf_cache`, `torch_cache`.

**Long jobs:** `GPU_SHELL_DETACH=1` or `-Detach`. Log under `/app/.agent/scratch/` or `/app/reports`. Do **not** use a bare `wsl … bash -lc` relay.

**GPU contention:** do not run heavy ML in `webui` and `gpu-shell` at the same time on an 8GB GPU.

## Do not

- Run dependency-using Python scripts in Windows PowerShell or CMD with the project’s Python (different env than gpu-shell/webui; DB/FFI/CUDA may fail).
- Default to Ubuntu `~/.venvs/tf` — that distro is optional and may be unregistered.
- Run the official WSL pytest suite (`pytest -m wsl`) in gpu-shell unless intended; that suite still uses **`~/.venvs/image-scoring-tests`** on Ubuntu when present.
- **Exception:** Scripts run via `run_webui_windows.bat` use Windows `.venv` — that is intentional.
