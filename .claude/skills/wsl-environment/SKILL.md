---
name: wsl-environment
description: Set up, run, and maintain the Docker + WSL2 environment image-scoring-backend depends on — gpu-shell for scripts/ML, docker-desktop Postgres/webui, optional Ubuntu ~/.venvs/tf and image-scoring-tests. Use when launching long GPU jobs, recovering from WSL instability, or provisioning Ubuntu. For which environment a single command needs, see wsl-tf-python-runner.
---

# Environment lifecycle — gpu-shell first, Ubuntu optional

## Authority & scope

Canonical env rules: root **`AGENTS.md`** and **`.cursor/rules/python-wsl-webapp-env.mdc`**. For *which environment a given command needs*, defer to **`wsl-tf-python-runner`**. This skill owns **provisioning, robust execution of long jobs, and recovery**.

## Topology (know this before touching anything)

| Layer | Role | If it stops |
|-------|------|-------------|
| **docker-desktop** | Docker Engine → Postgres, `image-scoring-webui`, **`image-scoring-gpu-shell`** | Postgres/webui/scripts go **down** |
| **Ubuntu** (optional) | `~/.venvs/tf`, `~/.venvs/image-scoring-tests`, `run_webui.bat` | Only host-WSL Python / `pytest -m wsl` die; **Postgres unaffected** |

> **Critical:** Postgres lives in **docker-desktop**, not Ubuntu. `wsl --shutdown` stops **all** distros incl. docker-desktop → **Postgres/webui/gpu-shell downtime**.

Day-to-day scripts and ML run in **`image-scoring-gpu-shell`**, not Ubuntu.

## Setup

**Verify gpu-shell first:**

```powershell
docker compose --profile gpu-shell up -d db gpu-shell
docker exec -i image-scoring-gpu-shell python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Bootstrap persistent `/root` extras (ultralytics, optional student scorer):

```powershell
docker exec -it image-scoring-gpu-shell bash /app/scripts/docker_gpu_shell_bootstrap.sh
```

**Ubuntu venvs** (only if that distro is registered — optional):

```bash
wsl -d Ubuntu bash -lc "cd /mnt/d/Projects/image-scoring-backend && bash ./scripts/wsl/setup_wsl_test_env.sh"
```

## Run — long-running / GPU jobs

Use **gpu-shell**, not a WSL host relay:

```powershell
.\scripts\powershell\Invoke-GpuShell.ps1 -Detach python scripts/backfill_bird_bbox.py --all-null
# or: $env:GPU_SHELL_DETACH=1; scripts\batch\docker_gpu_run.bat scripts/backfill_bird_bbox.py --all-null
```

Monitor from the **host** (log file / Postgres counts). Do not `wsl … sleep` loops.

**GPU contention:** the 8 GB GPU is shared with `image-scoring-webui`. Prefer one heavy job at a time.

**OOM:** bound in-flight decode memory. Confirm after the fact:

```powershell
docker exec image-scoring-gpu-shell dmesg 2>/dev/null | Select-String -Pattern "killed process|out of memory" | Select-Object -Last 5
```

## Maintain

### Health
```powershell
wsl.exe -l -v
docker ps --format "table {{.Names}}\t{{.Status}}"
docker exec image-scoring-gpu-shell nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader
```

### Recovery (decision tree)
1. **gpu-shell / webui down, docker-desktop Running** → `docker compose --profile gpu-shell up -d db gpu-shell` (and `up -d webui` if needed). **Preferred.**
2. **Ubuntu `Stopped`** → ignore unless you need `pytest -m wsl` / `run_webui.bat`.
3. **Full reset** (`wsl --shutdown`) → **confirm Postgres downtime** first, then restart Docker Desktop.

## Guardrails
- **Never** create venvs under `/mnt/...`.
- **Never** run `wsl --shutdown` to fix an Ubuntu-only problem.
- Don't claim a job "running" without confirming progress from the host (DB count / log growth).
- `.git/config` must stay standard — see root `AGENTS.md`.
