---
type: Architecture
title: Project Structure
description: Repository layout for image-scoring-backend — entry points, modules, scripts, tests, and docs.
resource: architecture/project-structure.md
tags: [docs, architecture, layout, scripts, okf]
timestamp: 2026-06-21T00:00:00Z
okf_version: 0.1
---

# Project Structure

**Last updated**: 2026-06-21

## Overview

This repository is organized so **user-facing entry points stay in the repo root**, while implementation code, scripts, tests, and documentation live in dedicated folders.

## Root (entry points)

Common entry points you’ll actually use:

- `run_scoring.bat`: **Universal Launcher** — Drag & Drop or Double-Click for GUI
- `Run-Scoring.ps1`: **Universal Logic** — Handles folders, files, and WSL routing
- `webui.py`: Web UI entry point
- `run_webui.bat`: batch wrapper for starting the Web UI
- `run_webui_docker.bat`: Docker-based Web UI wrapper
- `launch.py`: convenience launcher
- `mcp_config.json`: MCP server configuration (for Cursor / AI tooling)
- `README.md`: Main project overview and entry point
- `LICENSE`: License information

### External Repositories
- **[image-scoring-gallery](https://github.com/synthet/image-scoring-gallery)**: The high-performance standalone Electron gallery. Previously located in `electron-gallery/`.

## Core code

- `modules/`: application logic (DB, scoring, pipeline, UI, MCP server, etc.)
- `static/`: Web UI static assets
- `sql/`: SQL/migration scripts

## Scripts & automation

- `scripts/`: utilities, batch files, PowerShell scripts, and maintenance helpers
  - `scripts/python/`: Core batch processor (`batch_process_images.py`), single image scorer (`run_all_musiq_models.py`), gallery generator (`gallery_generator.py`), GUI wrapper (`scoring_gui.py`)
  - `scripts/powershell/`, `scripts/batch/`: Windows launchers and wrappers (e.g. `resume_recluster.bat`)
  - `scripts/maintenance/`: DB maintenance, backfill, cleanup scripts (culling backfills, EXIF, embeddings)
  - `scripts/research/`: CLIP culling experiments and rollout tools (`research/clip_culling/`)
  - `scripts/study/`: Agent-assisted cull study scripts (`agent_cull_*.py`)
  - `scripts/wsl/`: WSL test runner and agent CLI wrappers

Agent scratch (gitignored): `.agent/tmp/` (ephemeral probes), `.agent/study/runs/` (study matrix JSON).

When running scripts from the root directory, you may need to adjust paths or execute them from their respective subfolders. Example:
```powershell
.\scripts\powershell\process_nef_folder.ps1 -FolderPath "D:\Photos\..."
```

See also: [`scripts/README.md`](../../scripts/README.md) · [Culling embedding backfill runbook](../guides/CULLING_EMBEDDING_BACKFILL.md)

## Tests

- `tests/`: automated tests and verification scripts

## Models & weights

- `models/`: model assets and documentation
- `models/checkpoints/`: **local MUSIQ checkpoint directory** (large `.npz` files are not committed)

See:
- [models/checkpoints/README.md](../../models/checkpoints/README.md)
- [models/checkpoints/CHECKPOINTS_INFO.md](../../models/checkpoints/CHECKPOINTS_INFO.md)

## Documentation

All docs live under `docs/`.

- [Docs index](../INDEX.md)
- [Changelog](../../CHANGELOG.md)

Key subfolders:

- `docs/guides/getting-started/`: quick starts and how-tos
- `docs/guides/setup/`: Windows/WSL/CUDA setup
- `docs/technical/`: architecture + design notes
- `docs/reference/`: API and reference material
- `docs/ai/`: AI/agent context docs
- `docs/reports/`: research notes and analysis reports
- `docs/archive/`: historical/stale docs kept for reference

## Notes

- Some legacy docs may mention `musiq_original/` from older iterations of the project. **Current local checkpoint location is `models/checkpoints/`.**
