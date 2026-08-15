# Windows / WSL2 recommended split

## Windows host

Use for:

- VS Code / Cursor / Claude Desktop
- Docker Desktop (when driving compose from Windows)
- Simple search with `rg` / `fd` on Windows paths
- GitHub CLI (`gh`)
- Coordinating with sibling **image-scoring-gallery** (Electron) on Windows

## WSL2 Ubuntu (optional)

Use for:

- Official `pytest -m wsl` — `~/.venvs/image-scoring-tests`
- `run_webui.bat` when not using Docker WebUI
- Host tooling that still expects Ubuntu

**Default for backend scripts / `modules.*` / GPU:** Compose **`image-scoring-gpu-shell`** (`scripts\batch\docker_gpu_run.bat`).

## Backend workspace layout

Keep **image-scoring-backend** and **image-scoring-gallery** as sibling directories (e.g. `D:\Projects\` on Windows, `/mnt/d/Projects/` in WSL when needed).

| Task | Prefer |
|------|--------|
| Backend FastAPI / GPU scripts | **gpu-shell** (`docker_gpu_run.bat` / `Invoke-GpuShell.ps1`) |
| Gallery Electron (sibling repo) | Windows (see gallery repo) |
| PostgreSQL via Docker | WSL or Windows — run `docker compose` from backend repo |
| Agent file search | `rg`/`fd` or **project** **fff-be** MCP |

## Pitfalls

- **WSL2:** Keep active repos under `~/src` when possible — `/mnt/c` is slower for heavy I/O.
- **WSL2:** Debian/Ubuntu ship `fdfind`; symlink to `fd` (see [install-blocks.md](install-blocks.md)).
- **Windows:** Do not run backend Python with system Python — use gpu-shell.
- Avoid editing the same repo simultaneously from Windows and WSL if line-ending or file-watcher issues appear.

Cross-link: [`wsl-environment`](../../wsl-environment/SKILL.md) for long GPU jobs and recovery.
