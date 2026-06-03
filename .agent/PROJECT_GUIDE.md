# Agent Project Guide: Vexlum Scoring

This guide provides instructions for AI agents on how to navigate, maintain, and execute the **Vexlum Scoring** backend (`image-scoring-backend`).

## Backlog & queue (read first)

The canonical task queue is the **GitHub Project board** — not `TODO.md`:

**→ https://github.com/users/synthet/projects/1**

It spans `image-scoring-backend` and `image-scoring-gallery`. Every agent must follow the **five-step contract** in [`.cursor/skills/backlog-queue/SKILL.md`](../.cursor/skills/backlog-queue/SKILL.md): pick from `Stage = Ready` → `/task-claim <N>` → `In Progress` on first commit → `Blocked` (with comment) if stuck → PR with `Closes #<N>` → `Review` → `Done`.

`TODO.md` is a pointer only — never add tasks there.

## Documentation authority

Before changing API contracts, phase names, or schema: read **[`docs/CANONICAL_SOURCES.md`](../docs/CANONICAL_SOURCES.md)**. When editing or moving wiki pages under `docs/`, follow **[`docs/WIKI_SCHEMA.md`](../docs/WIKI_SCHEMA.md)** and append to **`docs/log.md`**.

**Agent infra:** catalog **[`AGENT_INFRA_INVENTORY.md`](AGENT_INFRA_INVENTORY.md)**, command list **[`COMMANDS.md`](COMMANDS.md)**, **[`SAFETY.md`](SAFETY.md)**, **[`subagents/README.md`](subagents/README.md)**, workflows under **[`workflows/`](workflows/)**, status **[`AGENT_INFRA_STATUS.json`](AGENT_INFRA_STATUS.json)**.

## Project Context
`image-scoring` is a multi-model quality assessment tool with a hybrid architecture (Windows + WSL 2). It uses TensorFlow and PyTorch for scoring, and PostgreSQL for storage.

## Core agent workflows

| Entry | Purpose | Path |
|-------|---------|------|
| Cursor slash commands | SDLC (`/spec`, `/plan`, `/implement`, `/pr-ready`, …) | [`.cursor/commands/`](../.cursor/commands/) — see [`.cursor/README.md`](../.cursor/README.md) |
| `/run_webui` (workflow) | Start the Web UI | `.agent/workflows/run_webui.md` |
| `/run_docker` (workflow) | Start the app in a container | `.agent/workflows/run_docker.md` |
| `/run_scoring` (workflow) | Run batch scoring via CLI | `.agent/workflows/run_scoring.md` |
| `/run_tests` (workflow) | Execute pytest suite | `.agent/workflows/run_tests.md` |
| `/verify_system` (workflow) | Check system health/models | `.agent/workflows/verify_system.md` |

## Technical Knowledge for Agents

### 1. Hybrid Environment Logic
- Most ML models **require** Linux/WSL for GPU acceleration.
- The application automatically handles path conversion (`/mnt/d` <-> `D:\`) in `modules/paths.py` or `modules/utils.py`.
- **CRITICAL**: Database locking restricts direct file access between Windows and WSL. **ALWAYS** use TCP connections (already implemented in `modules/db.py`).

### 2. Scoring Pipeline
- The pipeline uses a producer-consumer model (`modules/engine.py`).
- Models are located in `modules/` (e.g., `modules/topiq.py`, `modules/liqe.py`).
- Batch jobs are logged in `JOBS` and `IMAGES` tables.

### 3. Database Maintenance
- Schema migrations are handled in `modules/db.py` -> `init_db()`.
- If you add a new model score column, update `_init_db_impl`.

## Best Practices for Maintenance
- **Config**: Do not use hardcoded paths. Use `modules/config.py` which provides a central `BASE_DIR`.
- **Logging**: Use standard `logging` module. Avoid `print`.
- **Secrets**: External API keys go in `secrets.json` (ignored by git).

## Troubleshooting Flow
1. Run `/verify_system` to check CUDA and model weights.
2. Check `test_output.log` for recent failure details.
3. Verify PostgreSQL (port 5432) is running.
