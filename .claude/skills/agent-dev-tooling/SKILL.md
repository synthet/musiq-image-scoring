---
name: agent-dev-tooling
description: >-
  Backend build, test, lint, and verify workflows via gpu-shell, ruff,
  doctor, and docker compose. Use before claiming work complete or opening
  a PR. Do not invent ad hoc Python commands outside documented environments.
---

# Agent dev tooling

Task runners, lint, and verification for **image-scoring-backend** (Vexlum Scoring).

## Purpose

Run the correct project commands instead of inventing ad hoc toolchains. Primary stack: Python in **image-scoring-gpu-shell**.

## When to use

- After code changes: pytest subset, ruff, doctor
- Before `/pr-ready`: verification per AGENTS.md
- Docker Compose for Postgres or inference E2E
- Inspecting scripts under `scripts/` before running

## Required tools

- **Backend (primary):** Compose **`image-scoring-gpu-shell`** for app/scripts
- **WSL pytest `-m wsl`:** Ubuntu `~/.venvs/image-scoring-tests` when that distro exists
- **Lint:** `ruff`, optional `pyright` via uv tools
- **Ops:** `docker`, `docker compose`

Install baseline: [agent-cli-hub/references/install-blocks.md](../agent-cli-hub/references/install-blocks.md)

Full command list: [AGENTS.md](../../../AGENTS.md), [`.agent/COMMANDS.md`](../../../.agent/COMMANDS.md)

WSL venv selection: [`wsl-tf-python-runner`](../wsl-tf-python-runner/SKILL.md)

## Common commands (backend — gpu-shell first)

Fast CPU subset (from AGENTS.md), inside gpu-shell or documented test venv:

```powershell
scripts\batch\docker_gpu_run.bat -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py -q
```

Official WSL pytest suite (`-m wsl`):

```bash
bash ./scripts/wsl/run_wsl_tests.sh
```

Doctor / diagnostics:

```powershell
scripts\batch\docker_gpu_run.bat scripts/doctor.py --no-gpu
```

Lint:

```bash
ruff check modules/ --output-format=concise
```

Agent infra (when touching `.cursor/` assets):

```bash
python scripts/sync_assistant_trees.py --check
python scripts/ci/check_agent_frontmatter.py
python scripts/validate_cli_hub_skills.py
```

Docker (Postgres / profiles per AGENTS.md):

```bash
docker compose config
docker compose up -d
```

Postgres integration E2E (when explicitly requested):

```bash
RUN_POSTGRES_TESTS=1 pytest tests/integration/ -m postgres -v
```

## Agent-safe patterns

- Use WSL + correct venv before any `modules.*` import.
- Prefer marker-filtered pytest over full suite unless user asks.
- `docker compose down -v` and GPU jobs need confirmation.
- IPC/secrets rules: [`.agent/SAFETY.md`](../../../.agent/SAFETY.md).

## Commands requiring confirmation

- `ruff check --fix` on broad paths
- `docker compose down -v` (data loss)
- Postgres/integration E2E without user request
- Side-effecting MCP `dispatch` without `confirmed=True`

See [commands-requiring-confirmation.md](../agent-cli-hub/references/commands-requiring-confirmation.md).

## Troubleshooting

- **Import errors on Windows Python:** switch to WSL + `tf` venv.
- **Wrong pytest venv for `-m wsl`:** use `run_wsl_tests.sh`, not `tf` venv.
- **Doctor fails on DB:** document blocker; may need `docker compose up -d`.
- **Port 7860 listens but health fails (Connection reset / refused):** `docker ps` may show `image-scoring-webui` **Up** and the host socket still bound while the app inside is dead; `webui.lock` alone is not liveness evidence. Check `docker ps -a --filter name=image-scoring-webui`, `docker logs --tail 40 image-scoring-webui`, then `docker restart image-scoring-webui`. Poll until logs show `Uvicorn running on http://0.0.0.0:7860` and `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:7860/api/health` returns `200` (startup often takes 2–3 minutes for model/DB init — do not conclude failure on the first refusal).

## Verification checklist

```bash
python scripts/doctor.py --no-gpu
python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py -q --co -q | head
ruff check modules/ --output-format=concise
```
