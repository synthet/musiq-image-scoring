# Agent Project Guide: Image Scoring

This guide provides instructions for AI agents on how to navigate, maintain, and execute the Image Scoring project.

## Project Context
`image-scoring` is a multi-model quality assessment tool with a hybrid architecture (Windows + WSL 2). It uses TensorFlow and PyTorch for scoring, and PostgreSQL for storage.

## Core Agentic Skills (Commands)

| Command | Purpose | Workflow Path |
|---------|---------|---------------|
| `/run_webui` | Start the Gradio Web interface | `.agent/workflows/run_webui.md` |
| `/run_docker` | Start the app in a container | `.agent/workflows/run_docker.md` |
| `/run_scoring` | Run batch scoring via CLI | `.agent/workflows/run_scoring.md` |
| `/run_tests` | Execute pytest suite | `.agent/workflows/run_tests.md` |
| `/verify_system` | Check system health/models | `.agent/workflows/verify_system.md` |

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
