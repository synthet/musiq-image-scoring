---
name: agent-platform-tooling
description: >-
  Choose Windows native vs Docker gpu-shell vs WSL2 for agent shell work. Backend Python/GPU in image-scoring-gpu-shell; gh and light search on Windows. Use when picking where to run installs, tests, or MCP servers.
---

# Agent platform tooling

Windows host vs Docker gpu-shell vs optional WSL2 Ubuntu for coding agents in **image-scoring-backend** and sibling gallery workspace.

## Purpose

Pick the right environment before installing tools or running long jobs. Reduces path, performance, and line-ending issues.

## When to use

- Deciding where to run backend Python vs Windows-only tools
- Pytest/GPU/DB work vs GitHub CLI on Windows
- MCP servers that expect Unix paths
- Docker Compose from backend repo

## Required tools

Platform-specific — see [windows-wsl-split.md](../agent-cli-hub/references/windows-wsl-split.md) and [install-blocks.md](../agent-cli-hub/references/install-blocks.md).

Cross-links: [`wsl-environment`](../wsl-environment/SKILL.md), [`wsl-tf-python-runner`](../wsl-tf-python-runner/SKILL.md)

## Install

- **Windows:** winget block in [install-blocks.md](../agent-cli-hub/references/install-blocks.md)
- **WSL2:** apt + curl installers in same file

## Common commands

### Windows

```powershell
gh pr list --limit 10
rg "pattern" modules/ -n --max-count 30
```

### gpu-shell (backend default)

```powershell
docker compose --profile gpu-shell up -d db gpu-shell
scripts\batch\docker_gpu_run.bat scripts/doctor.py --no-gpu
```

### Switching context

See [windows-wsl-split.md](../agent-cli-hub/references/windows-wsl-split.md) for the full split diagram.

## When native Windows is enough

- `gh` issue/PR operations
- Simple `rg` / `fd` on `D:\Projects\...`
- Reading docs, editing small config with PowerShell
- Coordinating with gallery repo on Windows

## When gpu-shell is better

- **All backend Python** importing `modules.*`
- GPU scripts, backfills, doctor
- Docker Compose mirroring CI
- MCP stdio that can run in the container (`run_mcp_*_wsl.bat` now execs gpu-shell)

## When Ubuntu WSL2 is still required

- Official `pytest -m wsl` (`~/.venvs/image-scoring-tests`)
- `run_webui.bat` outside Docker

## Agent-safe patterns

- Store WSL clones under `~/src` for heavy I/O; use `/mnt/d/Projects` when sharing with Windows IDE.
- Do not run backend Python in Windows PowerShell with system Python — use gpu-shell.
- Set `LD_LIBRARY_PATH` for Firebird when DB/Firebird FFI involved — see `wsl-tf-python-runner`.

## Commands requiring confirmation

- Moving entire repo between Windows and WSL paths mid-task
- `wsl --unregister` or distro reset

## Troubleshooting

- **Slow rg on `/mnt/c`:** clone to `~/src/image-scoring-backend`.
- **Permission errors in WSL:** check ownership after Windows edits.
- **Docker not reachable from WSL:** ensure Docker Desktop WSL integration enabled.

## Verification checklist

Windows:

```powershell
Get-Command gh, rg, git, docker
docker exec image-scoring-gpu-shell python -c "import torch; print(torch.cuda.is_available())"
```
