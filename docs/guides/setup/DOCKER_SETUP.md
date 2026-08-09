---
type: Guide
title: Docker Setup
description: Install Docker Desktop / WSL tooling and run Postgres + WebUI via docker compose (Postgres primary).
resource: guides/setup/DOCKER_SETUP.md
tags: [docker, setup, postgres, gpu, wsl]
timestamp: 2026-08-09T04:45:00Z
okf_version: 0.1
---

# Docker Setup Guide

This guide covers Docker Desktop (WSL2 backend) and running Vexlum Scoring with Compose: **PostgreSQL + pgvector**, optional **`image-scoring-webui`**, and optional **`gpu-shell`** for GPU scripts/research.

For **Ubuntu vs `docker-desktop`**, Docker-only limits, and shutdown safety, see [wsl-vs-docker-topology.md](wsl-vs-docker-topology.md).

## Prerequisites

- Windows 10/11 with WSL2 enabled
- Ubuntu distribution installed in WSL2 (optional if you use Docker WebUI + `gpu-shell` only; still useful for host tooling — see [topology](wsl-vs-docker-topology.md))
- At least 10GB of free disk space
- (Optional) NVIDIA GPU for hardware acceleration
- **Docker Desktop**: Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) — ensure it uses the WSL 2 backend
- **PostgreSQL**: Provided by the Compose `db` service (`image-scoring-postgres`). No separate Windows DB install required for the default path.

---

## Part 1: Installing Docker in WSL2

### Quick Installation (Recommended)

Run the all-in-one installer from Windows:

```cmd
install_and_verify_docker.bat
```

This will:
1. Install Docker Engine in WSL
2. Configure sudo-less access
3. Install NVIDIA Container Toolkit for GPU support
4. Restart WSL and verify everything works

You'll be prompted for your sudo password during installation.

### Manual Installation

If you prefer to run each step manually:

#### Step 1: Install Docker Engine

```bash
cd /path/to/image-scoring
chmod +x scripts/install_docker_wsl.sh
./scripts/install_docker_wsl.sh
```

#### Step 2: Post-Installation Configuration

```bash
chmod +x scripts/setup_docker_postinstall.sh
./scripts/setup_docker_postinstall.sh
```

**Then restart WSL:**
```powershell
# From Windows PowerShell
wsl --shutdown
```

#### Step 3: Install NVIDIA Container Toolkit (GPU support)

```bash
chmod +x scripts/install_nvidia_docker.sh
./scripts/install_nvidia_docker.sh
```

> **Note:** Requires NVIDIA drivers installed on Windows (version 470+)

#### Step 4: Verify Installation

```bash
chmod +x scripts/verify_docker_wsl.sh
./scripts/verify_docker_wsl.sh
```

This checks: WSL2 environment, Docker installation, service status, non-sudo access, container functionality, Docker Compose, GPU access (if NVIDIA toolkit installed), disk space.

---

## Part 2: Running the Vexlum Scoring Scoring application

### Architecture

Compose runs **Postgres (pgvector)** and optional **FastAPI + Gradio** WebUI. Image libraries are bind-mounted (see [Scope paths](#scope-paths-runs--preview--indexing)). The Electron gallery runs on the Windows host and talks to the API/DB — not inside the webui container.

```mermaid
flowchart LR
    subgraph compose [Docker Compose]
        webui["image-scoring-webui\nFastAPI + Gradio :7860"]
        db["image-scoring-postgres\npgvector :5432"]
    end
    subgraph windows [Windows host]
        electron["Electron gallery"]
        photos["Photo library\nPHOTOS_BIND_SOURCE"]
    end
    webui --> db
    electron -->|"localhost:7860 / :5432"| webui
    electron --> db
    photos -->|"bind → /mnt/d/Photos"| webui
```

### Prerequisites

- **Docker Desktop for Windows** with the WSL 2 backend enabled
- **NVIDIA GPU + drivers 470+** (optional — required only for ML scoring in the container)
- Project cloned on your machine (sibling layout with **image-scoring-gallery** is typical)
- For Docker Desktop on Windows: set `PHOTOS_BIND_SOURCE` in `.env` (see [`.env.example`](../../../.env.example))

### First-time build

Build the Docker image once (and again whenever `requirements/requirements_wsl_gpu.txt` changes):

```bash
docker compose build
```

### Running

```bash
# Foreground — logs stream to the terminal
docker compose up

# Background (detached) — Postgres + WebUI
docker compose up -d db webui
```

Access the WebUI at **http://localhost:7860**. Postgres is on **localhost:5432** (`image_scoring` / see compose env).

### GPU shell (scripts / research)

Compose service **`gpu-shell`** (profile **`gpu-shell`**) reuses `image-scoring:latest` with CUDA, but **does not** start the WebUI. Use it instead of Ubuntu `~/.venvs/tf` for scripts, studies, and student-scorer work.

```bash
# Start Postgres + idle GPU shell
docker compose --profile gpu-shell up -d db gpu-shell

# Interactive shell
docker exec -it image-scoring-gpu-shell bash
# Windows: scripts\batch\docker_gpu_shell.bat

# One-shot Python (repo is /app)
docker exec -i image-scoring-gpu-shell python scripts/doctor.py --no-gpu
# Windows: scripts\batch\docker_gpu_run.bat scripts/doctor.py --no-gpu
```

**Mounts:** same `.:/app` and `PHOTOS_BIND_SOURCE` → `/mnt/d/Photos` as `webui`. Persistent Linux volumes: `gpu_shell_home` (`/root`), `hf_cache`, `torch_cache`.

**Research extras** (not baked into the image):

```bash
docker exec -it image-scoring-gpu-shell bash /app/scripts/docker_gpu_shell_bootstrap.sh
# Student scorer extras:
docker exec -e INSTALL_STUDENT_SCORER=1 -it image-scoring-gpu-shell bash /app/scripts/docker_gpu_shell_bootstrap.sh
# then: source /root/.venvs/research/bin/activate
```

**GPU contention:** avoid running heavy ML in `webui` and `gpu-shell` at the same time on an 8GB GPU — prefer one heavy job at a time.

**Long jobs:** log under `/app/reports` (repo bind); use detached `docker exec` rather than fragile host WSL relays.

### Stopping

```bash
docker compose down        # stops and removes the container (data is safe)
```

### Rebuilding after dependency changes

```bash
docker compose build && docker compose up
```

**Windows:** `docker_refresh_webui.bat` rebuilds the frontend SPA, runs `docker compose build webui`, recreates the container, and verifies agent-cull Gemini setup (`.env` / `GEMINI_CONFIG_SOURCE`). See [agent-cull-review-gemini-cli.md](agent-cull-review-gemini-cli.md).

### Updating Python code without rebuilding

The project root is live-mounted into the container (`.:/app`). Python source changes take effect on the next `docker compose restart webui` — no rebuild needed.

### Scope paths (Runs / preview / indexing)

The WebUI only sees filesystem paths **inside the container**. `docker-compose.yml` maps a **host** folder to **`/mnt/d/Photos`** inside `webui` via:

`${PHOTOS_BIND_SOURCE:-/mnt/d/Photos}:/mnt/d/Photos:rw`

- **Docker CLI in WSL**: Leaving `PHOTOS_BIND_SOURCE` unset uses `/mnt/d/Photos` on the WSL host, which matches typical drive mounts — paths like `/mnt/d/Photos/...` in **New Run** work.
- **Docker Desktop for Windows**: The default left-hand path is **not** your Windows `D:\` tree. Create a `.env` in the repo root (see [`.env.example`](../../../.env.example)) with e.g. `PHOTOS_BIND_SOURCE=D:/Photos` (forward slashes), then run `docker compose up -d --force-recreate webui`. Keep using `/mnt/d/Photos/...` in the UI; that is the path **inside** the container.

1. Set `PHOTOS_BIND_SOURCE` in `.env` when on Docker Desktop, or adjust `webui.volumes` if needed (e.g. `/mnt/e/Pictures:/mnt/e/Pictures:rw`, or a custom target and matching UI paths).
2. Run `docker compose up -d --force-recreate webui` after changing `.env` or compose volumes.
3. Use the **in-container** path in the scope field (`/mnt/d/Photos/...` when using the default right-hand mount).

Verify the bind: `docker exec image-scoring-webui ls /mnt/d/Photos`.

API errors for missing paths include a Docker reminder when `DOCKER_CONTAINER=1`.

### Key environment variables

These are set in `docker-compose.yml` and control the container's behaviour:

| Variable | Value | Purpose |
|---|---|---|
| `PHOTOS_BIND_SOURCE` | Optional; e.g. `D:/Photos` (Compose `.env`, not `config.json`) | **Host** folder bound to `/mnt/d/Photos` in `webui`; required for correct **New Run** paths on Docker Desktop for Windows |
| `GEMINI_CONFIG_SOURCE` | Optional; e.g. `C:/Users/you/.gemini` (Compose `.env`) | Host Gemini CLI OAuth dir mounted to `/root/.gemini` for [agent cull review](agent-cull-review-gemini-cli.md) |
| `GEMINI_CLI_TRUST_WORKSPACE` | `true` in `docker-compose.yml` | Allows headless Gemini CLI in the `webui` container |
| `POSTGRES_HOST` / `POSTGRES_*` | `db` / compose defaults | Primary database — Compose `db` service |
| `FIREBIRD_WIN_DB_PATH` | Legacy optional | Only if deliberately using Firebird; **not** required for Postgres-primary Docker |
| `FIREBIRD_CLIENT_LIBRARY` | Legacy optional | Bundled Linux `fbclient` path when Firebird is enabled |
| `DOCKER_CONTAINER` | `1` | Tells the app it is running inside Docker |
| `WEBUI_HOST` | `0.0.0.0` | Bind to all interfaces so port 7860 is reachable from Windows |

### Quick test (after installation)

```bash
# Basic Docker sanity check
docker run hello-world

# Test GPU access (if NVIDIA toolkit installed)
docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi

# Run the application
docker compose up
```

When the container starts you should see Postgres connectivity (Compose `depends_on` healthcheck) and, if configured, GPU detection in the logs (e.g., `NVIDIA GeForce RTX …`).

---

## Troubleshooting

### Docker service not starting

```bash
sudo service docker start
```

### Permission denied when running Docker

Complete Step 2 (post-installation) and restart WSL, or run `newgrp docker`.

### Postgres not reachable from WebUI / gallery

1. Confirm `image-scoring-postgres` is up: `docker ps` / Docker Desktop.
2. Check health: `docker exec image-scoring-postgres pg_isready -U postgres`.
3. From the host, connect to `localhost:5432` with the compose credentials (`image_scoring` DB).
4. Remember: `wsl --shutdown` stops **docker-desktop** and takes Postgres down — see [wsl-vs-docker-topology.md](wsl-vs-docker-topology.md#shutdown-safety).

### Legacy Firebird connection failed (optional path only)

Firebird is **decommissioned** for normal use. If you still force a Firebird path:

1. Verify the Firebird service on Windows (port 3050) and firewall (`setup_firewall.bat` as Administrator if needed).
2. Set `FIREBIRD_WIN_DB_PATH` with **forward slashes** and recreate: `docker compose down && docker compose up`.

### `duplicate key value violates unique constraint "jobs_pkey"` (`POST /api/runs/submit`)

PostgreSQL assigns `jobs.id` from a sequence (`SERIAL`). If you restored data, imported rows with explicit IDs, or migrated without resetting sequences, the sequence can lag behind `MAX(jobs.id)` and the next insert reuses an existing id.

**Fix — realign sequences** (same database your backend uses):

From the host, using the Compose Postgres service:

```bash
docker exec image-scoring-postgres psql -U postgres -d image_scoring -c "
SELECT setval(
  pg_get_serial_sequence('jobs', 'id'),
  COALESCE((SELECT MAX(id) FROM jobs), 1),
  true
);
"
```

To repair **all** SERIAL `id` columns the app uses (recommended after a full restore), run from the repo root (WSL / venv with project deps, same as the Firebird→Postgres migrate script):

```bash
python scripts/python/postgres_sequence_repair.py
```

You can pass `--pg-host`, `--pg-port`, `--pg-db`, `--pg-user`, `--pg-password` to override `config.json` / environment.

### New Run / scope preview: Path not found (`/mnt/d/Photos/...`)

The API checks paths **inside** the `webui` container. If the error mentions Docker and `PHOTOS_BIND_SOURCE`, the photos folder is not bind-mounted correctly.

1. Add `PHOTOS_BIND_SOURCE=<Windows path to library root>` to `.env` (see [`.env.example`](../../../.env.example)), e.g. `PHOTOS_BIND_SOURCE=D:/Photos`.
2. Run `docker compose up -d --force-recreate webui`.
3. Confirm: `docker exec image-scoring-webui ls /mnt/d/Photos` lists your top-level folders.

### No GPU detected

1. Verify `nvidia-smi` works in a standard WSL 2 terminal.
2. Check that `deploy.resources.reservations.devices` is present in `docker-compose.yml`.
3. Update NVIDIA drivers to the latest version.

### GPU not accessible in Docker containers

**Quick Fix:**
```cmd
cleanup_nvidia_repo.bat
fix_nvidia_docker.bat
```

Or from WSL:
```bash
cd /path/to/image-scoring
sudo rm -f /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo rm -f /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
./scripts/fix_nvidia_docker.sh
```

If `nvidia-smi` doesn't work in WSL: update NVIDIA drivers to 470+, run `wsl --update`, verify `nvidia-smi` in WSL first.

### Docker auto-start not working

Add to `~/.bashrc`:

```bash
if ! pgrep -x dockerd > /dev/null; then
    sudo service docker start > /dev/null 2>&1
fi
```

### Slow performance

Accessing files across Windows/WSL (e.g., `/mnt/d`) is slower than native Linux. For maximum performance, consider moving your workspace into the WSL filesystem.

---

## Uninstalling Docker

```bash
sudo service docker stop
sudo apt-get purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo rm -rf /var/lib/docker /etc/docker
sudo apt-get purge -y nvidia-container-toolkit
sudo groupdel docker
```

---

## Next Steps

- [wsl-vs-docker-topology.md](wsl-vs-docker-topology.md) — Ubuntu vs docker-desktop, Docker-only limits
- Review [docker-compose.yml](../../docker-compose.yml) for configuration options
- See [README.md](../../README.md) for application documentation
- [ENVIRONMENTS.md](ENVIRONMENTS.md) — WSL venvs when not using Docker WebUI
