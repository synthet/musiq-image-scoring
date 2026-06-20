# Project Memory


## Stable Project Facts

- Primary database is PostgreSQL + pgvector; Firebird is legacy.
- Python app/scripts that import `modules` or touch the DB should run in WSL with `~/.venvs/tf` unless documented otherwise (see AGENTS.md).
- Fast pytest subset: `python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py`.
- raw-sessions and dreams are gitignored; only memory.md/schema.md/config.json/CURSOR_USAGE.md are shared
- Gallery resolves backend URL via sibling `webui.lock` with `config.api` override (cross-repo).
- Gotcha narrative (env/test/SQL/git/multi-agent) lives in [`docs/LESSONS_LEARNED.md`](../docs/LESSONS_LEARNED.md); this file is the curated index. Every repo uses `docs/LESSONS_LEARNED.md` (OKF) as the standard lessons doc.

## User Preferences

- Prefer small, focused diffs; avoid drive-by refactors.
- Use the GitHub Project board for backlog (not TODO.md).

## Working Rules

- Read AGENTS.md and docs/CANONICAL_SOURCES.md before changing APIs, DB columns, or config keys.
- Never modify `.git/config` or commit secrets (`secrets.json`, real `.env`); do not set `extensions.worktreeConfig` (breaks embedded git libraries).
- Cross-repo DB/API contract changes require coordination with image-scoring-gallery.
- Dream never overwrites memory.md
- Use .agent-memory for team-shared project memory; Claude Code native memory is personal/ephemeral
- Official WSL pytest suite (`pytest -m wsl`) uses `~/.venvs/image-scoring-tests` via `Run-WSLTests.ps1`, not `~/.venvs/tf`.
- Design token changes start in `image-scoring-ui` `src/tokens.json`; bump backend/gallery consumers after `npm run build`.

## Recurring Issues

- `tests/test_probe.py` must be ignored in fast pytest runs (import-time DB calls).
- Ambiguous "E2E" wording: distinguish Postgres API E2E (`tests/integration`) vs Docker inference E2E (`tests/e2e_docker`).
- Fast pytest subset may also need `--ignore=tests/test_exifread.py` when `exifread` is not installed.

## Successful Patterns

- Read-only MCP triage before ad-hoc SQL or destructive fixes.
- Regenerate MCP tool inventory when `modules/mcp_server.py` tools change.
- Use MCP `search` then `dispatch` on `is-be-mcp` / `is-ui-mcp` before ad-hoc SQL or destructive fixes.
- Doc changes: OKF wiki ingest (`/wiki-ingest`) and append `docs/log.md` per docs-wiki skill.

## Open Questions

- (none yet — add via session logs and dream consolidation)

## Deprecated / Superseded

- (none yet)
