# Windows / WSL2 recommended split

## Windows host

Use for:

- VS Code / Cursor / Claude Desktop
- Docker Desktop (when driving compose from Windows)
- Simple search with `rg` / `fd` on Windows paths
- GitHub CLI (`gh`)
- Coordinating with sibling **image-scoring-gallery** (Electron) on Windows

## WSL2 Ubuntu

Use for:

- **image-scoring-backend** (primary) — Python, `~/.venvs/tf`, `~/.venvs/image-scoring-tests`
- `launch.py`, `webui.py`, anything importing `modules.*`
- Pytest with WSL markers — see [`wsl-tf-python-runner`](../../wsl-tf-python-runner/SKILL.md)
- Docker Compose workflows that expect Linux paths
- MCP stdio servers expecting Unix paths
- CI-like local test reproduction

## Backend workspace layout

Keep **image-scoring-backend** and **image-scoring-gallery** as sibling directories (e.g. `D:\Projects\` on Windows, `/mnt/d/Projects/` in WSL when needed).

| Task | Prefer |
|------|--------|
| Backend FastAPI / pytest / GPU scripts | WSL2 + documented venvs |
| Gallery Electron (sibling repo) | Windows (see gallery repo) |
| PostgreSQL via Docker | WSL or Windows — run `docker compose` from backend repo |
| Agent file search | `rg`/`fd` or user-level **fff** MCP |

## Pitfalls

- **WSL2:** Keep active repos under `~/src` when possible — `/mnt/c` is slower for heavy I/O.
- **WSL2:** Debian/Ubuntu ship `fdfind`; symlink to `fd` (see [install-blocks.md](install-blocks.md)).
- **Windows:** Do not run backend Python with system Python — use WSL + `~/.venvs/tf`.
- Avoid editing the same repo simultaneously from Windows and WSL if line-ending or file-watcher issues appear.

Cross-link: [`wsl-environment`](../../wsl-environment/SKILL.md) for long GPU jobs and recovery.
