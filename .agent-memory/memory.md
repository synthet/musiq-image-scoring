# Project Memory


## Stable Project Facts

- Primary database is PostgreSQL + pgvector; Firebird is legacy.
- Python app/scripts that import `modules` or touch the DB should run in WSL with `~/.venvs/tf` unless documented otherwise (see AGENTS.md).
- Fast pytest subset: `python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py`.
- raw-sessions and dreams are gitignored; only memory.md/schema.md/config.json/CURSOR_USAGE.md are shared

## User Preferences

- Prefer small, focused diffs; avoid drive-by refactors.
- Use the GitHub Project board for backlog (not TODO.md).

## Working Rules

- Read AGENTS.md and docs/CANONICAL_SOURCES.md before changing APIs, DB columns, or config keys.
- Never modify `.git/config` or commit secrets (`secrets.json`, real `.env`).
- Cross-repo DB/API contract changes require coordination with image-scoring-gallery.
- Dream never overwrites memory.md
- Use .agent-memory for team-shared project memory; Claude Code native memory is personal/ephemeral

## Recurring Issues

- `tests/test_probe.py` must be ignored in fast pytest runs (import-time DB calls).
- Ambiguous "E2E" wording: distinguish Postgres API E2E vs Docker inference E2E (see AGENTS.md).

## Successful Patterns

- Read-only MCP triage before ad-hoc SQL or destructive fixes.
- Regenerate MCP tool inventory when `modules/mcp_server.py` tools change.

## Open Questions

- (none yet — add via session logs and dream consolidation)

## Deprecated / Superseded

- (none yet)
