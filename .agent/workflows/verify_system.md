---
description: Verify backend environment — Postgres, config, doctor CLI, optional GPU
---

## Purpose

Confirm a machine can run **Vexlum Scoring** the way this repo expects: **PostgreSQL + pgvector** (primary), valid `config.json`, and Python deps in **WSL** for anything importing `modules.*`.

## When to use

- First-time setup, CI prep, or when doctor / WebUI fails to start.

## Canonical docs first

- [.agent/INFRA_QUICKSTART.md](../INFRA_QUICKSTART.md)
- [docs/DEVELOPMENT.md](../../docs/DEVELOPMENT.md)
- [docs/DIAGNOSTICS.md](../../docs/DIAGNOSTICS.md)
- [.cursor/rules/python-wsl-webapp-env.mdc](../../.cursor/rules/python-wsl-webapp-env.mdc)

## Safe commands (WSL, repo root)

1. **Activate app venv:** `source ~/.venvs/tf/bin/activate`
2. **Doctor (no GPU):** `python scripts/doctor.py --no-gpu`  
   - Full check (includes GPU probe when available): `python scripts/doctor.py`  
   - JSON: `python scripts/doctor.py --json`
3. **Optional:** `python -m pytest tests/test_doctor_cli.py` — fast CLI tests

## Files commonly touched

- `config.json` (local; not committed with secrets)
- `docker-compose.yml` / Postgres — if using containerized DB

## Tests / checks

- Doctor exit code **0** when no FAIL lines (see DIAGNOSTICS.md).
- If GPU scoring is in scope, run doctor **without** `--no-gpu` once CUDA stack is installed.

## Common failure modes

- **DB unreachable:** Postgres not running or wrong `database.postgres.*` in `config.json`.
- **Wrong interpreter:** Running scripts from Windows PowerShell instead of WSL + `tf` venv for `modules` imports.
- **pgvector missing:** Doctor reports extension; apply per DATABASE.md / DEVELOPMENT.md.

## Do not

- Do not treat **SQLite** / `scoring_history.db` as the primary store (legacy docs only).
- Do not commit `secrets.json` or real DB passwords.
