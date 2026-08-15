---
name: wsl-tf-python-runner
description: Runs Python, scripts, and tests the way image-scoring-backend expects — Compose gpu-shell (image-scoring-gpu-shell) for app/scripts/modules/DB/ML, optional Ubuntu ~/.venvs/tf, separate ~/.venvs/image-scoring-tests for pytest -m wsl. Use when running scripts under scripts/, anything importing modules.*, resolving Windows vs Docker vs WSL Python confusion, or choosing the correct pytest environment and markers.
---

# gpu-shell / Python runner

## Authority

Canonical environment rules live in root **AGENTS.md** (Commands, Testing, Cursor Cloud notes) and **`.cursor/rules/python-wsl-webapp-env.mdc`** (always applied). State which table row applies before proposing commands.

## Which environment

| Task | Environment | Notes |
|------|-------------|--------|
| Scripts, `modules.*`, DB, config, ML | **`image-scoring-gpu-shell`** | `scripts\batch\docker_gpu_run.bat` or `Invoke-GpuShell.ps1` |
| Web UI | **`image-scoring-webui`** | `docker compose up -d db webui` |
| Web UI (Ubuntu, optional) | `~/.venvs/tf` (WSL) | `run_webui.bat` only if Ubuntu is registered |
| Pytest tests marked **`wsl`** | Ubuntu + `~/.venvs/image-scoring-tests` | `scripts/wsl/run_wsl_tests.sh` or `Run-WSLTests.ps1` — skip if Ubuntu is missing |
| Fast CPU-only subset (no GPU/DB/ML/Firebird) | Per AGENTS.md | still use the venv/container the project documents |
| Web UI on Windows native only | Project **`.venv`** | `run_webui_windows.bat` — exception path |

When in doubt for anything touching **`modules`**, the database, or CUDA: **gpu-shell**.

## Proposed commands (copy-paste)

```powershell
docker compose --profile gpu-shell up -d db gpu-shell
scripts\batch\docker_gpu_run.bat scripts/doctor.py --no-gpu
.\scripts\powershell\Invoke-GpuShell.ps1 python scripts/backfill_bird_bbox.py --all-null
.\scripts\powershell\Invoke-GpuShell.ps1 -Detach python scripts/backfill_bird_bbox.py --all-null
```

Inside the container:

```bash
docker exec -i -w /app -e PYTHONPATH=/app image-scoring-gpu-shell python scripts/doctor.py --no-gpu
```

**Official `wsl` pytest suite** (Ubuntu required — do not claim green without this when `-m wsl` matters):

```powershell
.\scripts\powershell\Run-WSLTests.ps1
```

## Pytest markers

Definitions are in **`pytest.ini`**. Do **not** assert that tests passed without running them in the **intended** environment for that marker (especially **`wsl`** → Ubuntu `image-scoring-tests` venv).

## Behavior constraints

- **Prefer giving commands** and environment clarification; open **readonly false** only when the user needs a script or project file edit.
- If execution cannot complete in the current session, state what failed (command, stderr snippet) and the **minimal** fix (start Docker Desktop, `docker compose --profile gpu-shell up -d db gpu-shell`, set `PHOTOS_BIND_SOURCE` in `.env`).
- Do not default to `wsl -e bash` + `~/.venvs/tf`. Ubuntu may be unregistered.

## Cursor note

There is no user-pluggable **Task** subagent type in Cursor; this **skill** is the supported way to bundle the same behavior. Users can **@mention** `wsl-tf-python-runner` or rely on the description for auto-selection.
