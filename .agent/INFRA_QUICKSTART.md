# Infra quick reference (humans & agents)

Single-page checklist; MCP details stay in [AGENTS.md](../AGENTS.md).

## Project purpose

AI image scoring, tagging, clustering, and gallery APIs — Python backend (FastAPI + Postgres + pgvector), optional GPU models.

## Safe commands (repo root)

- `python scripts/doctor.py` — config + DB + pgvector (+ optional GPU); WSL + `~/.venvs/tf` per [docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md).
- `python scripts/export_debug_bundle.py` — redacted zip for support (review before sharing).
- `python -m pytest tests/test_doctor_cli.py` — fast infra unit tests.
- `ruff check scripts/doctor.py scripts/export_debug_bundle.py modules/doctor_cli.py` — lint touched files.

## After substantive code changes

- Run the **narrowest pytest** that covers your change; for broad regressions see [docs/TESTING.md](../docs/TESTING.md).
- Prefer **WSL + `~/.venvs/tf`** for anything importing `modules.*` or touching the DB (see `.cursor/rules/python-wsl-webapp-env.mdc`).

## Architecture notes

- **Postgres** is the primary DB; **Firebird** is legacy.
- **Embeddings:** 1280-d MobileNetV2 default space — [docs/EMBEDDINGS.md](../docs/EMBEDDINGS.md) → technical page.
- **Phases:** `indexing` → `metadata` → `scoring` → `culling` → `keywords` — [docs/technical/PIPELINE_TERMINOLOGY.md](../docs/technical/PIPELINE_TERMINOLOGY.md).

## Known pitfalls

- **`modules/db.py`** — very large; avoid drive-by edits.
- **Keywords / Phase 4** — use `update_image_metadata` / normalized tables; see CLAUDE.md.
- **EXIF / NEF / orientation** — regression-sensitive; see [docs/technical/NEF_IMPLEMENTATION_REVIEW.md](../docs/technical/NEF_IMPLEMENTATION_REVIEW.md).
- **Do not assume GPU** — CPU paths exist; doctor reports CUDA as optional.

## Do not

- Commit `secrets.json`, real `.env`, or machine-specific passwords.
- Add large binary fixtures to git.
- Rewrite Alembic migrations casually.

## Debugging

- [docs/DIAGNOSTICS.md](../docs/DIAGNOSTICS.md) — doctor, bundles, logs, MCP tools.
- [docs/TROUBLESHOOTING.md](../docs/TROUBLESHOOTING.md) — hub links.
- [.agent/AGENT_INFRA_INVENTORY.md](AGENT_INFRA_INVENTORY.md) — catalog of agent-facing rules, skills, workflows (see also [COMMANDS.md](COMMANDS.md), [SAFETY.md](SAFETY.md), [workflows/](workflows/)).

## Electron gallery (sibling repo)

- `npm run doctor` in **image-scoring-gallery** — Node + `config.json` + `webui.lock`.
- Gallery [AGENTS.md](https://github.com/synthet/image-scoring-gallery/blob/main/AGENTS.md) for **`gallery`** MCP.
