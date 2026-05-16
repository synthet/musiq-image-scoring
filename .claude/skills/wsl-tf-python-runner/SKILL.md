---
name: wsl-tf-python-runner
description: Runs Python, scripts, and tests the way image-scoring-backend expects — WSL, ~/.venvs/tf for app and scripts that import modules/DB/ML, separate ~/.venvs/image-scoring-tests for pytest -m wsl. Use when running webui.py, scripts under scripts/, anything importing modules.*, resolving Windows vs WSL Python confusion, or choosing the correct pytest environment and markers.
---

# WSL / tf Python runner

## Authority

Canonical environment rules live in root **AGENTS.md** (Commands, Testing, Cursor Cloud notes) and **`.cursor/rules/python-wsl-webapp-env.mdc`** (always applied). State which table row applies before proposing commands.

## Which environment

| Task | Environment | Notes |
|------|-------------|--------|
| Web UI, `webui.py`, `scripts/**`, `modules.*`, DB, config, ML | **WSL** + `~/.venvs/tf` | Same as `run_webui.bat` inner WSL setup |
| Pytest tests marked **`wsl`** | **WSL** + `~/.venvs/image-scoring-tests` | `scripts/wsl/run_wsl_tests.sh` or `scripts/powershell/Run-WSLTests.ps1` — **not** `tf` unless intentional |
| Fast CPU-only subset (no GPU/DB/ML) | Per AGENTS.md | e.g. `pytest -m "not gpu and not db and not ml"` — still use the venv the project documents for that command |
| Web UI on Windows native only | Project **`.venv`** | `run_webui_windows.bat` — exception path |

When in doubt for anything touching **`modules`**, the database, or pgvector: **WSL + `tf`**.

## Proposed commands (copy-paste)

Replace `REPO_WSL` with the repo's WSL path (example: `/mnt/d/Projects/image-scoring-backend`). Replace drive letter if the project is not on `D:`.

**Examples:**

```bash
cd /mnt/d/Projects/image-scoring-backend && source ~/.venvs/tf/bin/activate && python webui.py
```

```bash
cd /mnt/d/Projects/image-scoring-backend && source ~/.venvs/tf/bin/activate && python -m pytest -m "not gpu and not db and not ml"
```

**Official `wsl` pytest suite** (correct venv — do not claim green without this when `-m wsl` matters):

```bash
cd /mnt/d/Projects/image-scoring-backend && bash ./scripts/wsl/run_wsl_tests.sh
```

From Windows PowerShell (delegates to WSL):

```powershell
.\scripts\powershell\Run-WSLTests.ps1
```

Optional setup if the test venv is missing: `bash ./scripts/wsl/setup_wsl_test_env.sh` (see script and AGENTS.md).

## Pytest markers

Definitions are in **`pytest.ini`** (`gpu`, `db`, `ml`, `wsl`, `network`, `sample_data`, `postgres`, `inference_e2e`). Do **not** assert that tests passed without running them in the **intended** venv for that marker (especially **`wsl`** → `image-scoring-tests` venv via the scripts above).

## Behavior constraints

- **Prefer giving commands** and environment clarification; open **readonly false** only when the user needs a script or project file edit.
- If execution cannot complete in the current session, state what failed (command, stderr snippet) and the **minimal** fix (e.g. create venv, start Docker Postgres, set `LD_LIBRARY_PATH`, run from WSL not Windows).

## Cursor note

There is no user-pluggable **Task** subagent type in Cursor; this **skill** is the supported way to bundle the same behavior. Users can **@mention** `wsl-tf-python-runner` or rely on the description for auto-selection.
