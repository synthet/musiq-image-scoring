---
type: Guide
title: WSL vs Docker topology
description: "Operator map of Ubuntu WSL vs docker-desktop: what runs where, Docker-only limits, shutdown safety, photo binds."
resource: guides/setup/wsl-vs-docker-topology.md
tags: [wsl, docker, setup, postgres, gpu]
timestamp: 2026-08-09T04:39:52Z
okf_version: 0.1
---

# WSL vs Docker topology

On Windows, this project uses **two WSL2 distros** plus the Windows host. They are not interchangeable. Day-to-day scoring + Postgres + **GPU scripts/research** can run entirely under Docker (`db` / `webui` / `gpu-shell`). Ubuntu WSL remains optional for host Python and `pytest -m wsl`. Electron gallery stays on Windows.

Related: [ENVIRONMENTS.md](ENVIRONMENTS.md) (Python venvs), [DOCKER_SETUP.md](DOCKER_SETUP.md) (compose build/run, GPU shell), [WINDOWS_WSL_DEPLOYMENT.md](WINDOWS_WSL_DEPLOYMENT.md).

## Distro map

| Layer | Typical identity | Role |
|-------|------------------|------|
| **Ubuntu** | Default WSL distro; disk often under `D:\WSL\Ubuntu\ext4.vhdx` | Optional host for `~/.venvs/tf`, `~/.venvs/image-scoring-tests`, `run_webui.bat` when not using Docker |
| **docker-desktop** | Managed by Docker Desktop | Docker Engine → Compose (`image-scoring-postgres`, `image-scoring-webui`, **`image-scoring-gpu-shell`**, e2e profiles) |
| **Windows host** | Native | Electron gallery (**image-scoring-gallery**), Docker Desktop UI, PowerShell wrappers |

```mermaid
flowchart TB
  subgraph win [Windows host]
    gallery["Electron gallery"]
    dd["Docker Desktop"]
  end
  subgraph ubuntu [Ubuntu WSL]
    tf["~/.venvs/tf\nwebui / scripts / ML"]
    tests["~/.venvs/image-scoring-tests"]
  end
  subgraph ddesk [docker-desktop WSL]
    engine["Docker Engine"]
    pg["image-scoring-postgres :5432"]
    webui["image-scoring-webui :7860"]
    shell["image-scoring-gpu-shell"]
  end
  dd --> engine
  engine --> pg
  engine --> webui
  engine --> shell
  gallery -->|"HTTP / webui.lock"| webui
  gallery -->|"pg or API SQL"| pg
  tf -->|"optional host client"| pg
  shell --> pg
```

**Check state:** `wsl.exe -l -v` — Ubuntu and `docker-desktop` list separately (`Running` / `Stopped`).

## Operator decision table

| Goal | Enough to run | Notes |
|------|---------------|-------|
| Postgres only | `docker compose up -d db` (or keep `image-scoring-postgres` up) | Ubuntu may stay **Stopped** |
| Scoring WebUI + DB (Docker-first) | `image-scoring-postgres` + `image-scoring-webui` | Ubuntu optional; GPU via NVIDIA Container Toolkit / Desktop GPU |
| Scoring WebUI (WSL-first) | Ubuntu + `~/.venvs/tf` via `run_webui.bat` | Still needs Postgres (usually Docker) |
| Ad-hoc scripts / `modules.*` / research / student scorer | **`gpu-shell`** (Compose profile) | Prefer over Ubuntu; see [DOCKER_SETUP — GPU shell](DOCKER_SETUP.md#gpu-shell-scripts--research). Ubuntu + `~/.venvs/tf` still works |
| Official `pytest -m wsl` | Ubuntu + `~/.venvs/image-scoring-tests` | See [WSL Tests](../../testing/WSL_TESTS.md) |
| Docker inference E2E | Compose profile `e2e-inference` | Separate from Postgres API E2E; see AGENTS.md |
| Browse / cull in desktop UI | **Windows** Electron gallery | Gallery Compose image exists but is secondary; prefer `npm run dev` |
| “Everything in Docker only” | **Not** full product (gallery + Docker Engine WSL remain) | Scripts/research **can** use `gpu-shell` without Ubuntu |

## Can Ubuntu stay stopped?

**Yes**, when you only need Compose Postgres, `image-scoring-webui`, and/or **`image-scoring-gpu-shell`**. Rebooting or leaving Ubuntu **Stopped** does **not** stop `docker-desktop` containers.

**No**, when you need WSL host Python (`run_webui.bat` outside Docker, official `pytest -m wsl`).

## Shutdown safety

| Action | Effect |
|--------|--------|
| Leave Ubuntu **Stopped**; keep Docker Desktop running | **Preferred** for Docker-first ops — Postgres/webui/gpu-shell stay up |
| Cold-start Ubuntu (`wsl -d Ubuntu …`) | Boots Ubuntu only; **no** intentional DB downtime |
| `wsl --shutdown` | Stops **all** WSL distros including **docker-desktop** → **Postgres and webui go down** |
| Compact / move VHDX / change `.wslconfig` | Usually requires `wsl --shutdown` — coordinate downtime first |

After a full shutdown: start Docker Desktop, wait for containers (`docker ps`), then start Ubuntu only if needed.

Never use `wsl --shutdown` to “fix” an Ubuntu-only problem — restart or re-enter Ubuntu instead.

## Photo library binds (`PHOTOS_BIND_SOURCE`)

The WebUI and **`gpu-shell`** only see paths **inside** the container. Compose maps a **host** folder to **`/mnt/d/Photos`** for both `webui` and `gpu-shell`:

```text
${PHOTOS_BIND_SOURCE:-/mnt/d/Photos}:/mnt/d/Photos:rw
```

| How you run Compose | What to set |
|---------------------|-------------|
| Docker CLI **inside Ubuntu** | Often leave unset — default `/mnt/d/Photos` matches the WSL drive mount |
| **Docker Desktop for Windows** | Set in repo `.env` (see [`.env.example`](../../../.env.example)): e.g. `PHOTOS_BIND_SOURCE=D:/Photos` (forward slashes) |

UI / API **New Run** scope paths stay as **in-container** paths (`/mnt/d/Photos/...`). After changing `.env` or volumes: `docker compose up -d --force-recreate webui`. Verify: `docker exec image-scoring-webui ls /mnt/d/Photos`.

Optional thumbnail path rebasing: `IMAGE_SCORING_HOST_PROJECT_WSL` / `IMAGE_SCORING_HOST_PROJECT_WIN` in `.env` (see compose comments).

Details and troubleshooting: [DOCKER_SETUP.md — Scope paths](DOCKER_SETUP.md#scope-paths-runs--preview--indexing).

## Database note (Postgres primary)

Compose **`db`** (`image-scoring-postgres`, pgvector) is the **primary** database. Firebird is **decommissioned** for normal operation; compose may still expose legacy `FIREBIRD_*` env vars for optional/legacy paths — do not treat a Windows Firebird service as a prerequisite for Docker WebUI + Postgres.

## Quick commands

```powershell
wsl.exe -l -v
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

```bash
# Ubuntu app stack (when not using Docker webui)
source ~/.venvs/tf/bin/activate
cd /mnt/d/Projects/image-scoring-backend   # adjust drive/path
python launch.py
```

```bash
# Docker-first stack (from repo root on Windows or WSL)
docker compose up -d db webui

# GPU scripts / research (does not start WebUI)
docker compose --profile gpu-shell up -d db gpu-shell
# or: scripts\batch\docker_gpu_shell.bat
```
