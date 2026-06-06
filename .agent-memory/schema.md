# Agent memory schema

## Session log (YAML in `raw-sessions/`)

Each file is named `YYYY-MM-DDTHHMMSSZ.yaml` (UTC).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `timestamp` | string (ISO-8601 UTC) | yes | When the session ended |
| `task_summary` | string | yes | One-line description of work |
| `files_touched` | list of strings | no | Paths inspected or changed |
| `commands_run` | list of strings | no | Shell commands (no secrets) |
| `tests_run` | list of strings | no | Test commands |
| `test_results` | string | no | Pass/fail/skip summary |
| `key_decisions` | list of strings | no | Architectural or approach choices |
| `errors_or_blockers` | list of strings | no | Failures encountered |
| `final_outcome` | string | no | How the session ended |
| `memory_candidates` | list of objects | no | Items for consolidation (see below) |

### `memory_candidates[]`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | yes | Proposed memory line |
| `category` | enum | yes | See categories below |
| `confidence` | enum | yes | `low`, `medium`, `high` |
| `source_hint` | string | no | Optional note (e.g. issue #) |

### Categories

- `stable_fact` — Durable architecture/stack facts
- `user_preference` — Long-lived style or workflow preferences
- `working_rule` — How agents should operate in this repo
- `recurring_issue` — Repeated traps, flaky tests, env problems
- `successful_pattern` — Approaches that worked well
- `open_question` — Unverified assumptions
- `deprecated` — Superseded guidance (audit only)

## Approved memory (`memory.md`)

Markdown with fixed H2 sections (order matters for parsing):

1. `## Stable Project Facts`
2. `## User Preferences`
3. `## Working Rules`
4. `## Recurring Issues`
5. `## Successful Patterns`
6. `## Open Questions`
7. `## Deprecated / Superseded`

Bullet lines use `- ` prefix. Empty section: `- (none yet)`.

## Dream proposal (`dreams/*.md`)

YAML front matter between `---` delimiters:

```yaml
generated_at: ISO-8601
source_sessions: [list of raw session filenames]
item_counts: {section: count}
```

Body uses the same H2 sections as `memory.md`.

## Changelog (`dreams/*-changelog.md`)

Sections: `## Added`, `## Updated`, `## Removed`, `## Deprecated`, `## Uncertain / needs review`

Each entry: bullet with text and optional `(from: session-file.yaml)`.
