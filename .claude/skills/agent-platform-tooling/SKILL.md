---
name: agent-platform-tooling
description: >-
  Choose Windows native vs WSL2 for agent shell work. Backend Python/GPU,
  pytest, and Unix-path MCP in WSL2; gh and light search on Windows. Use when
  picking where to run installs, tests, or MCP servers.
---

# Agent platform tooling

Windows host vs WSL2 Ubuntu for coding agents in **image-scoring-backend** and sibling gallery workspace.

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

### WSL2 (backend default)

```bash
cd ~/src/image-scoring-backend   # or /mnt/d/Projects/image-scoring-backend
source ~/.venvs/tf/bin/activate
python scripts/doctor.py --no-gpu
bash ./scripts/wsl/run_wsl_tests.sh
```

### Switching context

See [windows-wsl-split.md](../agent-cli-hub/references/windows-wsl-split.md) for the full split diagram.

## When native Windows is enough

- `gh` issue/PR operations
- Simple `rg` / `fd` on `D:\Projects\...`
- Reading docs, editing small config with PowerShell
- Coordinating with gallery repo on Windows

## When WSL2 is better

- **All backend Python** importing `modules.*`
- Pytest (especially `-m wsl`, GPU, DB, ML markers)
- Docker Compose mirroring CI
- MCP stdio servers expecting Linux paths
- Bash maintenance under `scripts/wsl/`

## Agent-safe patterns

- Store WSL clones under `~/src` for heavy I/O; use `/mnt/d/Projects` when sharing with Windows IDE.
- Do not run backend Python in Windows PowerShell with system Python.
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
Get-Command gh, rg, git
```

WSL:

```bash
python3 --version; source ~/.venvs/tf/bin/activate && python --version; which rg fd git
```
