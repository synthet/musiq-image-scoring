# Command quick reference — image-scoring-backend

Verified patterns from [AGENTS.md](../AGENTS.md), [.agent/INFRA_QUICKSTART.md](INFRA_QUICKSTART.md), and [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md). **Default for `modules.*` / DB / ML:** Compose **`image-scoring-gpu-shell`** ([.cursor/rules/python-wsl-webapp-env.mdc](../.cursor/rules/python-wsl-webapp-env.mdc)). Ubuntu `~/.venvs/tf` is optional.

## Setup

- GPU scripts: `docker compose --profile gpu-shell up -d db gpu-shell`
- One-shot: `scripts\batch\docker_gpu_run.bat scripts/doctor.py --no-gpu`
- Interactive: `scripts\batch\docker_gpu_shell.bat`
- PostgreSQL (typical): `docker compose up -d` from repo root
- DB migrations: `alembic upgrade head` (when schema changes) — run via gpu-shell if you need the app env

## Diagnostics

- `scripts\batch\docker_gpu_run.bat scripts/doctor.py` — config + DB + pgvector (+ optional GPU probe)
- `scripts\batch\docker_gpu_run.bat scripts/doctor.py --no-gpu` — skip GPU checks
- `scripts\batch\docker_gpu_run.bat scripts/doctor.py --json` — machine-readable output
- Redacted support bundle: `python scripts/export_debug_bundle.py` (review zip before sharing)
- Auto-drive monitor: `python scripts/diagnostics/monitor_drive.py --once` (poll `GET /api/runs/drive/status`; add `--local-diagnostics` in WSL app env)

## Development server

- From Windows: `docker compose up -d db webui` (day-to-day) or `run_webui.bat` if Ubuntu is installed
- From WSL (repo root, venv on): `python launch.py` or `python webui.py`
- MCP beside WebUI: `ENABLE_MCP_SERVER=1 python webui.py` (Linux/WSL)

## Tests / lint

- Fast subset: `python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py`
- If collection fails on optional deps: add `--ignore=tests/test_exifread.py` per [AGENTS.md](../AGENTS.md)
- WSL-marked tests: use `~/.venvs/image-scoring-tests` via `scripts/wsl/run_wsl_tests.sh` or `Run-WSLTests.ps1`
- Lint touched Python: `ruff check <paths>`

## Docs / wiki

- Authority: [docs/CANONICAL_SOURCES.md](../docs/CANONICAL_SOURCES.md), [docs/WIKI_SCHEMA.md](../docs/WIKI_SCHEMA.md), [docs/OKF_ADOPTION.md](../docs/OKF_ADOPTION.md)
- OKF lint: `python scripts/okf_lint.py --profile vexlum --exclude-prefix archive/`
- OKF changed docs (CI): `python scripts/ci/okf_lint_changed.py --base origin/main --fail-on error`
- Combined wiki lint: `python scripts/wiki_lint.py --exclude-prefix archive/`
- Gallery docs (sibling): `python scripts/okf_lint.py ../image-scoring-gallery/docs --profile vexlum`
- Slash commands: `/wiki-ingest`, `/wiki-lint`, `/wiki-query` (see `.cursor/commands/`)
- Skill: `.cursor/skills/docs-wiki/SKILL.md`
- After substantive doc moves: append [docs/log.md](../docs/log.md)

## MCP / support

- Tool schemas: `mcps/<server>/tools/<tool>.json` (see [.cursor/rules/mcp-schema-check.mdc](../.cursor/rules/mcp-schema-check.mdc))
- Read-only triage: see [.agent/workflows/safe_mcp_diagnostics.md](workflows/safe_mcp_diagnostics.md) and [.cursor/rules/image-scoring-mcp.mdc](../.cursor/rules/image-scoring-mcp.mdc)

## Cross-repo (with gallery)

- Contract order: [.agent/workflows/cross_repo_contract_change.md](workflows/cross_repo_contract_change.md)
- Gallery doctor (sibling): `npm run doctor` in **image-scoring-gallery**

## Inventory maintenance

- Regenerate MCP table in AGENTS.md when tools change: `python scripts/generate_mcp_tool_inventory.py --update-docs AGENTS.md docs/technical/MCP_DEBUGGING_TOOLS.md`

## Agent CLI skills

```bash
python scripts/validate_cli_hub_skills.py   # after changing .cursor/skills/agent-* or mcp-code-intelligence
python scripts/sync_assistant_trees.py --check
```

Spec: [.agent/cli-tools-skills-spec.md](cli-tools-skills-spec.md).
