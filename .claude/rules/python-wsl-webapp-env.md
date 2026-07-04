---
description: Which Python environment to use for app, scripts, and tests; run dependency-using code in WSL with ~/.venvs/tf
alwaysApply: true
---

# Python Environments — When to Use What

Use the environment that matches what you are running. **Default for app and scripts: WSL + `~/.venvs/tf`.**

## Quick decision

| What you're doing | Environment | How to run |
|-------------------|-------------|------------|
| **Web UI** | `~/.venvs/tf` (WSL) | `run_webui.bat` or from WSL: `source ~/.venvs/tf/bin/activate && python launch.py` |
| **Web UI (Windows native)** | `.venv` (project root) | `run_webui_windows.bat` |
| **Any script that uses `modules`, DB, config, or ML** (e.g. `scripts/`, `webui.py`, `launch.py`) | `~/.venvs/tf` (WSL) | In WSL: `source ~/.venvs/tf/bin/activate` then `python <script>`. From Windows: use existing `.bat`/`.ps1` wrappers or `wsl -e bash -c "..."` with that venv. |
| **Pytest tests marked `wsl`** | `~/.venvs/image-scoring-tests` (WSL) | `scripts/wsl/run_wsl_tests.sh` or `Run-WSLTests.ps1` (they activate this venv). Do **not** use `~/.venvs/tf` for pytest unless you intentionally want the app stack. |
| **Windows-native, CPU-only** (no GPU, no VILA) | `.venv` (project root) | Optional. Activate `.venv` in PowerShell/CMD and run `python launch.py` or scripts. No script in the repo uses this by default. |

When in doubt (e.g. running a script under `scripts/` that imports `modules` or touches the DB): use **WSL + `~/.venvs/tf`**.

---

# Run Python in WSL (Webapp Environment)

When running Python scripts that use project dependencies (e.g. `modules.*`, database, config, MCP), **always run them in WSL** using the same environment as the webapp: **`~/.venvs/tf`**.

## Reference

The webapp is started via **`run_webui.bat`**, which:

1. Converts the project root to a WSL path (e.g. `D:\Projects\image-scoring` → `/mnt/d/Projects/image-scoring`).
2. Runs in WSL with:
   - **Venv**: `source ~/.venvs/tf/bin/activate`
   - **Firebird lib**: `LD_LIBRARY_PATH` includes `PROJECT_ROOT/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib`
   - **MCP**: `ENABLE_MCP_SERVER=1` (optional for scripts)

## How to run scripts

- **WebUI**: Use **`run_webui.bat`** (or from WSL with the same env: `python launch.py`).
- **Other Python scripts** (under `scripts/`, or any script that imports `modules` or uses the DB): Run in **WSL** with the same environment.

  **From a WSL terminal** (recommended): open WSL, go to project root (e.g. `cd /mnt/d/Projects/image-scoring`), then:

  ```bash
  export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib
  source ~/.venvs/tf/bin/activate
  python scripts/path/to/script.py
  ```

  **From Windows (PowerShell/CMD)** — run the script via WSL (replace `d` in `/mnt/d/` if your project is on another drive):

  ```powershell
  wsl -e bash -c "cd /mnt/d/Projects/image-scoring && export LD_LIBRARY_PATH=\$LD_LIBRARY_PATH:/mnt/d/Projects/image-scoring/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib && source ~/.venvs/tf/bin/activate && python scripts/path/to/script.py"
  ```

- Prefer using a **WSL terminal** at project root with venv and `LD_LIBRARY_PATH` set once, then running `python script.py` as needed.

## Do not

- Run dependency-using Python scripts in Windows PowerShell or CMD with the project’s Python (different env than webapp; DB/FFI may fail).
- Assume the system or a different venv has the same packages or Firebird setup as `~/.venvs/tf` in WSL.
- Run the official WSL pytest suite (`pytest -m wsl`) in `~/.venvs/tf` unless intended; use **`~/.venvs/image-scoring-tests`** via `scripts/wsl/run_wsl_tests.sh` or `Run-WSLTests.ps1` for the documented test setup.
- **Exception:** Scripts run via `run_webui_windows.bat` use Windows `.venv` — that is intentional.
