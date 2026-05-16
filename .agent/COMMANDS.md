# Command quick reference — image-scoring-backend

Verified patterns from [AGENTS.md](../AGENTS.md), [.agent/INFRA_QUICKSTART.md](INFRA_QUICKSTART.md), and [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md). **Default for `modules.*` / DB / ML:** WSL + `source ~/.venvs/tf/bin/activate` ([.cursor/rules/python-wsl-webapp-env.mdc](../.cursor/rules/python-wsl-webapp-env.mdc)). On Windows host paths, translate to `/mnt/<drive>/Projects/...` inside WSL.

## Setup

- Create / activate app venv (WSL): `source ~/.venvs/tf/bin/activate`
- Install deps: see [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md) and `requirements/`
- PostgreSQL (typical): `docker compose up -d` from repo root (if your setup uses Compose)
- DB migrations: `alembic upgrade head` (when schema changes)

## Diagnostics

- `python scripts/doctor.py` — config + DB + pgvector (+ optional GPU probe)
- `python scripts/doctor.py --no-gpu` — skip GPU checks
- `python scripts/doctor.py --json` — machine-readable output
- Redacted support bundle: `python scripts/export_debug_bundle.py` (review zip before sharing)

## Development server

- From Windows: `run_webui.bat` (WSL inside)
- From WSL (repo root, venv on): `python launch.py` or `python webui.py`
- MCP beside WebUI: `ENABLE_MCP_SERVER=1 python webui.py` (Linux/WSL)

## Tests / lint

- Fast subset: `python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py`
- If collection fails on optional deps: add `--ignore=tests/test_exifread.py` per [AGENTS.md](../AGENTS.md)
- WSL-marked tests: use `~/.venvs/image-scoring-tests` via `scripts/wsl/run_wsl_tests.sh` or `Run-WSLTests.ps1`
- Lint touched Python: `ruff check <paths>`

## Docs / wiki

- Authority: [docs/CANONICAL_SOURCES.md](../docs/CANONICAL_SOURCES.md), [docs/WIKI_SCHEMA.md](../docs/WIKI_SCHEMA.md)
- After substantive doc moves: append [docs/log.md](../docs/log.md)

## MCP / support

- Tool schemas: `mcps/<server>/tools/<tool>.json` (see [.cursor/rules/mcp-schema-check.mdc](../.cursor/rules/mcp-schema-check.mdc))
- Read-only triage: see [.agent/workflows/safe_mcp_diagnostics.md](workflows/safe_mcp_diagnostics.md) and [.cursor/rules/image-scoring-mcp.mdc](../.cursor/rules/image-scoring-mcp.mdc)

## Cross-repo (with gallery)

- Contract order: [.agent/workflows/cross_repo_contract_change.md](workflows/cross_repo_contract_change.md)
- Gallery doctor (sibling): `npm run doctor` in **image-scoring-gallery**

## Inventory maintenance

- Regenerate MCP table in AGENTS.md when tools change: `python scripts/generate_mcp_tool_inventory.py --update-docs AGENTS.md docs/technical/MCP_DEBUGGING_TOOLS.md`
