---
name: agent-memory
description: Log agent sessions, consolidate project memory (dream), promote reviewed memory, and load context for new chats. Use when ending a session, improving cross-session recall, or when the user mentions agent memory, dream, log-session, or memory.md.
---

# Agent memory

Local consolidation for **image-scoring-backend** — external artifacts only (no model training).

## When to use

- **Session start:** Read `.agent-memory/memory.md`; prefer repo evidence on conflict.
- **Session end / milestone:** Log durable learnings with `/log-session`.
- **Periodic:** Run `/dream-memory`, review changelog, `/promote-memory` after human approval.

## Memory candidates

Use `text|category|confidence` on CLI or YAML `memory_candidates`:

| Category | Use for |
|----------|---------|
| `stable_fact` | Stack, architecture, env |
| `user_preference` | Style, workflow, review prefs |
| `working_rule` | How to run tests, what not to touch |
| `recurring_issue` | Flakes, traps, env pain |
| `successful_pattern` | Approaches that worked |
| `open_question` | Unverified assumptions |
| `deprecated` | Superseded guidance |

Confidence: `low`, `medium`, `high`.

## Commands (repo root)

```powershell
python scripts/agent-memory/log_session.py --summary "..." --outcome "..." --candidate "text|working_rule|high"
python scripts/agent-memory/import_transcripts.py --dry-run --cursor-projects "$env:USERPROFILE\.cursor\projects"
python scripts/agent-memory/dream.py
python scripts/agent-memory/promote_dream.py --dream .agent-memory/dreams/<timestamp>.md
python scripts/agent-memory/context.py
```

## Transcript import (v2)

- Slash command: `/import-transcripts`
- Config: `scripts/transcript_mining/workspace_map.json`, `repo_profiles.json`
- Staging: `.agent/scratch/transcript-mining/<repo>/REVIEW.md` (gitignored)
- Tier A: `--write-sessions` → `dream.py` → human promote; Tier B/C: `docs/LESSONS_LEARNED.md`
- See [docs/technical/AGENT_MEMORY.md](../../docs/technical/AGENT_MEMORY.md) § v2

## Dream review checklist

1. Open `dreams/*-changelog.md` — scan **Uncertain / needs review**.
2. Diff proposed `dreams/*.md` vs `memory.md`.
3. Redact anything sensitive; reject promotion if secrets might be present.
4. Promote only when the proposal is accurate and concise.

## Safety

- Scripts block common secret patterns on write.
- Do not log `secrets.json`, `.env`, tokens, or personal library paths.
- Never edit `memory.md` directly during implementation work.

## Reference

- [`.agent-memory/CURSOR_USAGE.md`](../../.agent-memory/CURSOR_USAGE.md)
- [`.agent-memory/schema.md`](../../.agent-memory/schema.md)
- [docs/technical/AGENT_MEMORY.md](../../docs/technical/AGENT_MEMORY.md)
