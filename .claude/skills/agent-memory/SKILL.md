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
python scripts/agent-memory/dream.py
python scripts/agent-memory/promote_dream.py --dream .agent-memory/dreams/<timestamp>.md
python scripts/agent-memory/context.py
```

## Dream review checklist

1. Open `dreams/*-changelog.md` — scan **Uncertain / needs review**.
2. Check **Stale / needs re-verification** — re-validate each flagged item (last confirmed > 180 days ago) or promote as `deprecated` if superseded.
3. Diff proposed `dreams/*.md` vs `memory.md`.
4. Redact anything sensitive; reject promotion if secrets might be present.
5. Promote only when the proposal is accurate and concise.

## Relationship to Claude Code native memory

Two memory stores coexist; keep them in their lanes:

- **`.agent-memory/memory.md` (this skill)** — team-shared, committed, repo-scoped, review-gated. Durable project facts useful to *any* agent or human. This is the source of truth that ships in the repo.
- **Claude Code native `~/.claude/.../memory/MEMORY.md`** — private to this machine/account, auto-loaded each session, holds personal recall and in-flight context.

Rule of thumb: if a learning belongs to the project, route it here via `/log-session` → `/dream-memory` → `/promote-memory`. If it is personal/ephemeral, leave it in native memory. When they conflict, committed `.agent-memory/memory.md` and live repo evidence win.

## Safety

- Scripts block common secret patterns on write.
- Do not log `secrets.json`, `.env`, tokens, or personal library paths.
- Never edit `memory.md` directly during implementation work.
- `raw-sessions/` and `dreams/` are gitignored; only `memory.md`, `schema.md`, `config.json`, and `CURSOR_USAGE.md` are shared.

## Reference

- [`.agent-memory/CURSOR_USAGE.md`](../../.agent-memory/CURSOR_USAGE.md)
- [`.agent-memory/schema.md`](../../.agent-memory/schema.md)
- [docs/technical/AGENT_MEMORY.md](../../docs/technical/AGENT_MEMORY.md)
