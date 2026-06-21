---
type: Lessons Learned
title: Lessons Learned — image-scoring-backend
description: Hard-won environment, test-triage, SQL, git, and multi-agent gotchas distilled from agent session history.
resource: docs/LESSONS_LEARNED.md
tags: [lessons, agent, wsl, testing, database, okf]
timestamp: 2026-06-16T00:00:00Z
okf_version: 0.1
---

# Lessons Learned — image-scoring-backend

Hard-won lessons distilled from agent session history (Claude Code + Cursor).
These complement `CLAUDE.md`, `AGENTS.md`, and the `.agent-memory/` system —
this file is the "why it bit us" narrative, not the canonical reference. The
curated index in [`.agent-memory/memory.md`](../.agent-memory/memory.md) points
here for the full gotcha narrative. When something here graduates into a rule,
move it to the appropriate canonical doc and link back.

> Scope note: many items below are *environment* and *workflow* traps that
> recur across sessions. The `wsl-environment` and `wsl-tf-python-runner`
> skills own the lifecycle details; this file records the failure modes that
> motivated them.

## Environment & execution

### Bash tool runs Windows-side; it cannot see `/mnt/d`
The Bash tool executes on the Windows host. It **cannot** reach WSL paths like
`/mnt/d/...`. To run anything that imports `modules.*`, touches the DB, or needs
the ML stack, go through PowerShell into WSL:

```
wsl -e bash -lc "cd /mnt/d/Projects/image-scoring-backend && source ~/.venvs/tf/bin/activate && python ..."
```

PowerShell can reach both `D:\` and WSL; the Bash tool reaches neither WSL nor
the GPU venv. Pick the tool by what the command needs, not by habit.

### Which venv
- `~/.venvs/tf` — the app, `scripts/`, and anything importing `modules.*`/ML.
  In several sessions this was the **only** venv present.
- `~/.venvs/image-scoring-tests` — `pytest -m wsl`. Do **not** assume it exists;
  some sessions found it absent.
- Windows `.venv\` (`D:\Projects\image-scoring-backend\.venv`) — has `ruff` and
  `python` for fast lint/unit work on the host.

### Postgres ports
- `5432` — prod / config-pointed DB.
- `5433` — E2E test DB (`image_scoring_test`). A *connection refused* on 5433
  during a plain unit run is **harmless noise**, not a failure.
- `db_postgres.get_pg_config()` honors `POSTGRES_HOST` / `POSTGRES_PORT` /
  `POSTGRES_DB` env vars — use those to point tests at the right instance.

## Test triage

### `D:/Photos` vs `/mnt/d/Photos` path-test failures are NOT your bug
The single most repeated false alarm. `convert_path_to_local` rewrites
`/mnt/d` → `D:/` on Windows, so path-normalization tests **fail on the Windows
host and pass under WSL**. Before "fixing" them:
1. Re-run under WSL `~/.venvs/tf`, or
2. `git stash` and confirm they fail identically without your changes.

They are host artifacts, not regressions. Run the canonical suite in WSL.

### Coarse-mtime drvfs → config-cache cross-test contamination
WSL `/mnt/d` (drvfs) has coarse mtime resolution. The config cache keys on mtime,
so tests that write config files can contaminate each other and fail only in the
full suite (pass in isolation). Fix landed as a **global autouse fixture**
`_isolate_config_cache` in `tests/conftest.py` — don't reintroduce per-file
`_clear_config_cache` fixtures that duplicate it.

### "Pass in isolation, fail in the full suite" = shared global state
Treat this signature as cache/singleton contamination first, not a logic bug.

## Database / SQL gotchas

Check `information_schema` before assuming a column name. Recurring real columns
that bit us:
- `image_model_scores.normalized` — **not** `normalized_score`.
- `image_phase_status.last_error` and `image_phase_status.attempt_count`.
- `file_size`, `error_message`, `ml_phase`, `cull_failed` did **not** exist where
  assumed.

Postgres-specific: **you cannot reference a SELECT alias in `ORDER BY`/`HAVING`** —
repeat the expression or group by it. Postgres POSIX regex does **not** support
`\d`; use `[0-9]`.

### Pooled-connection read-only safety
`PGConnectionManager.__exit__` must roll back on any non-commit path and guard
commit/rollback/release in `try/except` so a borked session never returns to the
pool dirty. For read-only work, `set_session(readonly=True)` and **restore it in
`finally` before releasing** the connection.

### Phantom scores (finalization gap)
There is a real gap between `ScoringWorker` persisting per-model
`image_model_scores` rows and `ResultWorker` writing `score_general` +
`set_image_phase_status(SCORING, DONE)`. An interruption in between leaves rows
scored but the image phantom-incomplete. The old
`reconcile_phantom_complete_image_phases` only flips the phase — it never writes
`score_general`. `modules/phantom_score_finalize.py` /
`scripts/maintenance/finalize_phantom_scores.py` close it.

## Git & shell quoting

### Don't put PowerShell here-strings in the Bash tool
Using `@'...'@` (PowerShell here-string) inside a Bash-tool commit produced a
stray leading `@ ` on the subject and trailing `@`. For multi-line commit
messages, write the message to a temp file and `git commit -F file` (then delete
it). Same class of bug as bash quoted heredocs mangling backslashes — when in
doubt, write the payload to a file with the Write tool instead of inlining it.

### Inline `python -c` with nested quotes fails under PowerShell
The `--json` dry-run with an inline `python -c` broke on unmatched quotes. Fall
back to non-JSON output piped through `grep`, or move the script into a file.

## Working alongside other agents

### Concurrent-agent contamination is real
Parallel sessions (a Gemini agent, betrayed by `gallery-mcp.lock` and
`scripts/wsl/gemini_agent.sh` appearing) edited in-scope files mid-run. Defenses
that worked:
- Only stage/commit files matching the **user-approved scope** at each step.
- Re-run tests/`tsc` **immediately before** each commit so the snapshot is
  internally consistent (not half-written).
- After staging, verify there are no further unstaged modifications to staged
  files before pushing.
- Flag out-of-scope WIP to the user; don't sweep it into your commit.

### The "201 ruff errors" alarm
A big ruff count is usually **pre-existing legacy debt** in the
`db_legacy.py` / `db_postgres.py` monoliths (unused imports, etc.). Verify your
*new* files lint clean and that the error count is identical between `master`
and the working tree — then leave the pre-existing debt alone (minimal-diff).

### MCP write tools are not auto-allowed
Attempts to add `execute_sql` write entries to `.claude/settings.json` were
denied. Don't assume write-capable MCP tools are available; prefer the
read-only diagnostics profile and ask before enabling writes.
