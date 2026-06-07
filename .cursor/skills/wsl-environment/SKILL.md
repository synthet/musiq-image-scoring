---
name: wsl-environment
description: Set up, run, and maintain the WSL2 environment image-scoring-backend depends on — Ubuntu distro, ~/.venvs/tf (app/scripts/ML) and ~/.venvs/image-scoring-tests (pytest -m wsl), GPU/CUDA passthrough, Docker Desktop Postgres, Firebird libs. Use when provisioning the venvs, launching long-running GPU jobs robustly, or recovering from WSL instability (Wsl/Service/E_UNEXPECTED, distro Stopped, OOM-kill, disk bloat). For which venv a single command needs, see wsl-tf-python-runner; this skill owns the environment lifecycle.
---

# WSL environment — setup, run, maintain

## Authority & scope

Canonical env rules: root **`AGENTS.md`** (Commands, Testing, Gotchas) and **`.cursor/rules/python-wsl-webapp-env.mdc`**. For *which venv/marker a given command needs*, defer to the **`wsl-tf-python-runner`** skill. This skill owns **provisioning, robust execution of long jobs, and recovery/maintenance**.

Default repo path in WSL: `/mnt/d/Projects/image-scoring-backend` (adjust the drive if relocated).

## Topology (know this before touching anything)

| Distro | Role | If it stops |
|--------|------|-------------|
| **Ubuntu** | GPU/ML venvs, runs `webui.py`, `scripts/**`, `modules.*` | App/ML jobs die; **Postgres unaffected** |
| **docker-desktop** | Docker Engine → **Postgres `image_scoring` on `127.0.0.1:5432`**, webui container | Postgres/webui go **down** |

> **Critical:** Postgres lives in the **docker-desktop** distro, not Ubuntu. You can reboot Ubuntu freely (no DB impact). `wsl --shutdown` stops **all** distros incl. docker-desktop → **Postgres/webui downtime** — only use it when truly required (see Recovery).

Venvs live on **ext4 inside the distro** (`~/.venvs/...`), never on `/mnt/<drive>` (Windows FS venvs are extremely slow / can hang).

| Venv | Purpose |
|------|---------|
| `~/.venvs/tf` | App, `scripts/**`, anything importing `modules.*`, DB, ML (torch+CUDA, open_clip, timm, transformers) |
| `~/.venvs/image-scoring-tests` | `pytest -m wsl` suite only |

## Setup

**Verify first** (most "setup" requests just need a health check, §Maintain → Health):
```bash
wsl -d Ubuntu bash -lc "source ~/.venvs/tf/bin/activate && python -c 'import torch; print(torch.__version__, torch.cuda.is_available())'"
```

**Create the test venv** (idempotent helper, installs requirements + firebird-driver):
```bash
wsl -d Ubuntu bash -lc "cd /mnt/d/Projects/image-scoring-backend && bash ./scripts/wsl/setup_wsl_test_env.sh"
```

**Provision the `tf` venv** (when missing). Python **3.12** can't use the base `requirements.txt` (pins `tensorflow-cpu<2.16` — incompatible); use the WSL GPU requirements:
```bash
wsl -d Ubuntu bash -lc "python3 -m venv ~/.venvs/tf && source ~/.venvs/tf/bin/activate && \
  python -m pip install --upgrade setuptools wheel && \
  cd /mnt/d/Projects/image-scoring-backend && \
  python -m pip install -r requirements/requirements_wsl_gpu.txt"
```
GPU/ML extras (open_clip, timm, transformers, pyiqa, torch CUDA build) are installed as the relevant features need them; confirm with the CUDA check above. Firebird is legacy/decommissioned — only install `firebird-driver` (and set `LD_LIBRARY_PATH` to the `fbclient` dir) if a task explicitly touches Firebird.

## Run — long-running / GPU jobs

For a one-off command use the `wsl-tf-python-runner` pattern. For **anything that runs minutes+ under GPU/IO load** (backfills, batch embedding, full pipeline), follow these rules — they encode failures hit in production:

1. **Detach from the host relay.** A bare `wsl … bash -lc "<longjob>"` dies if the WSL host-side relay hiccups (`Wsl/Service/E_UNEXPECTED`), even though the distro survives. Launch detached so it reparents to init:
   ```bash
   wsl -d Ubuntu bash -lc "cd /mnt/d/Projects/image-scoring-backend && source ~/.venvs/tf/bin/activate && \
     setsid bash -c 'python -u -m scripts.<job> >> reports/<job>.log 2>&1' < /dev/null & disown; echo launched"
   ```
   `nohup` alone is not enough — it survives session exit but not relay teardown; `setsid` + `</dev/null` is what detaches it.
2. **Monitor from the host, not WSL.** Long-lived `wsl … "sleep N; …"` commands stress the same fragile relay and can themselves trigger `E_UNEXPECTED`. Poll the **host-side Postgres (5432)** or `tail` the log via short, separate commands. A host poller (Git Bash) example:
   ```bash
   PY="D:/Projects/image-scoring-backend/.venv/Scripts/python.exe"
   for i in $(seq 1 30); do "$PY" check_progress.py; sleep 30; done
   ```
3. **Budget GPU + host RAM.** The 8 GB GPU is shared with the webui container; load models sequentially at fp16. **Host RAM is the usual OOM cause** — loading many full-res RAW/NEF decodes at once balloons RSS and the Linux OOM-killer sends SIGTERM (job exits 15). Bound in-flight memory (downscale images on load, smaller chunk/batch). Confirm an OOM after the fact:
   ```bash
   wsl -d Ubuntu bash -lc "dmesg 2>/dev/null | grep -iE 'killed process|out of memory' | tail -5"
   ```

## Maintain

### Health
```bash
wsl.exe -l -v                                  # distro states (Running/Stopped)
wsl -d Ubuntu bash -lc "uptime && nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader"
wsl -d Ubuntu bash -lc "source ~/.venvs/tf/bin/activate && python -c 'import torch;print(torch.cuda.is_available())'"
```
A growing Ubuntu `uptime` with no reboot means the VM is stable; a job dying while `uptime` keeps climbing points at the **relay**, not the distro.

### Recovery (decision tree)
1. **Ubuntu `Stopped`, docker-desktop `Running`** → just rerun any `wsl -d Ubuntu …` command; it cold-boots Ubuntu. **No DB downtime.** Re-launch the (resumable) job. **Preferred path.**
2. **Relay wedged** (even short `bash -lc` returns `E_UNEXPECTED`) but distros listed `Running` → retry once; the relay often clears. Avoid long WSL commands meanwhile.
3. **Full reset needed** (both distros wedged, or `.wslconfig` change) → `wsl --shutdown` then restart Docker Desktop. **This stops Postgres/webui** — confirm with the user first unless they've authorized downtime, then verify recovery with `docker ps`.

```powershell
wsl --shutdown          # LAST resort — stops docker-desktop (Postgres) too
# then start Docker Desktop; wait for containers, check: docker ps
```

### Resource / disk maintenance (elevated Windows PowerShell, not WSL bash)
- Reclaim NTFS space after deleting files in Linux (ext4.vhdx stays large): `scripts/powershell/Compact-WslVhdx.ps1` (runs `wsl --shutdown` first).
- Relocate distros off C: → D:: `scripts/powershell/Move-WslToD.ps1`.
- Cap WSL memory to prevent host starvation: create `%USERPROFILE%\.wslconfig` with `[wsl2]\nmemory=12GB\nswap=8GB`, then `wsl --shutdown` to apply (DB downtime — coordinate).

## Guardrails
- **Never** create venvs under `/mnt/...`; always `~/.venvs/...` on ext4.
- **Never** run `wsl --shutdown` to fix an Ubuntu-only problem — reboot Ubuntu instead (docker-desktop/Postgres stay up).
- Don't claim a job "running" without confirming progress from the host (DB count / log growth), and don't claim tests green unless run in the marker's intended venv (see `wsl-tf-python-runner`).
- `.git/config` must stay standard (no worktree extensions) — see root `AGENTS.md`.

## Cursor note

Use this skill for **environment lifecycle** (provision venvs, detach long GPU jobs, WSL recovery, disk maintenance). For a **single** Python command or pytest run, prefer **`wsl-tf-python-runner`**. Users can **@mention** `wsl-environment` or rely on the description for auto-selection; the **`.cursor/agents/wsl-environment.md`** subagent bundles the same behavior for Task delegation.
