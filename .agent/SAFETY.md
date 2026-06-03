# Agent safety and hygiene — image-scoring-backend

## Secrets and credentials

- Never commit `secrets.json`, real `.env`, API keys, or connection strings with passwords.
- Never paste live credentials into prompts, logs, or MCP tool arguments when avoidable.

## Debug bundles

- Support zip only via `python scripts/export_debug_bundle.py` (redacted; excludes `secrets.json`).
- Treat every bundle as **possibly sensitive** until you manually review; do not attach unreviewed zips to public tickets.

## Generated and local artifacts

- Do not commit thumbnails, caches, model weights, large binaries, personal scratch scripts, or machine-specific paths.
- Avoid adding bulk outputs under `output/`, `backups/`, or similar unless the repo explicitly expects them (prefer `.gitignore`).

## Contracts and terminology

- Do not invent REST paths, payload fields, DB column names, `phase_code` values, or `config.json` keys. Use [docs/CANONICAL_SOURCES.md](../docs/CANONICAL_SOURCES.md).
- Pipeline vocabulary: [docs/technical/PIPELINE_TERMINOLOGY.md](../docs/technical/PIPELINE_TERMINOLOGY.md).

## Database

- **PostgreSQL + pgvector** is primary; Firebird is legacy. Do not assume SQLite for current deployments ([docs/DATABASE.md](../docs/DATABASE.md)).
- Prefer read-only SQL via MCP `execute_sql` for triage; avoid ad-hoc destructive SQL without an issue and backup plan.

## RAW / NEF / EXIF

- Changes to RAW preview, NEF handling, or EXIF orientation are regression-sensitive. Add or extend tests; see [docs/technical/NEF_IMPLEMENTATION_REVIEW.md](../docs/technical/NEF_IMPLEMENTATION_REVIEW.md) and related RAW docs in CANONICAL_SOURCES.

## MCP

- Treat `execute_code`, `set_config_value`, `run_processing_job`, and other write-capable tools as **high risk**. Prefer read-only diagnostics unless the user explicitly requests writes ([.agent/workflows/safe_mcp_diagnostics.md](workflows/safe_mcp_diagnostics.md)).
- On shared machines, SSE MCP attaches to a live WebUI; do not assume an isolated process.

## External CLI reviews (subagent-orchestrator)

- Review-only: never set `allowWrites: true` on `run_subagent` (rejected in v0.1).
- Selected source files are sent to **Codex / Gemini** per their provider policies; do not use for proprietary code you cannot export.
- Never include `secrets.json`, `.env`, credentials, or full `config.json` in `task`, `files`, or `extraContext`.
- Outputs land in `.agent-runs/` (gitignored); treat as sensitive until reviewed.
- See [docs/technical/EXTERNAL_CLI_REVIEWS.md](../docs/technical/EXTERNAL_CLI_REVIEWS.md).

## Git

- Never modify `.git/config` or add non-standard extensions (see AGENTS.md / CLAUDE.md).

## Docs

- Prefer small linked pages over monolithic dumps.
- After wiki-affecting edits, update indexes per [docs/WIKI_SCHEMA.md](../docs/WIKI_SCHEMA.md) and append [docs/log.md](../docs/log.md).
