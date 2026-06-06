# Agent memory consolidation

**Status:** Shipped (v1, deterministic merge). **Authority for daily use:** [`.agent-memory/CURSOR_USAGE.md`](../../.agent-memory/CURSOR_USAGE.md).

## Purpose

Improve AI coding sessions over time via **external** memory artifacts — not model weight changes. The workflow:

1. **Log** structured session notes (`raw-sessions/`, gitignored by default).
2. **Dream** merge candidates into a proposed `memory.md` + changelog (`dreams/`, gitignored).
3. **Promote** after human review into approved [`.agent-memory/memory.md`](../../.agent-memory/memory.md).

## Layout

| Path | Git | Role |
|------|-----|------|
| `.agent-memory/memory.md` | Tracked | Approved project memory |
| `.agent-memory/schema.md` | Tracked | YAML session + markdown section spec |
| `.agent-memory/config.json` | Tracked | Limits and retention |
| `.agent-memory/raw-sessions/` | Ignored | Per-session YAML logs |
| `.agent-memory/dreams/` | Ignored | Proposals and changelogs |

## Implementation

- Package: [`scripts/agent_memory/`](../../scripts/agent_memory/)
- CLIs: [`scripts/agent-memory/`](../../scripts/agent-memory/)
- Tests: [`tests/test_agent_memory.py`](../../tests/test_agent_memory.py)

## Agent integration

- Rule: `.cursor/rules/agent-memory.mdc` (mirrored `.claude/rules/`)
- Skill: `.cursor/skills/agent-memory/SKILL.md` (mirrored `.claude/skills/`)
- Commands: `/log-session`, `/dream-memory`, `/promote-memory`, `/memory-context`

## v1 limitations

- No automatic import of Cursor agent transcripts.
- Consolidation merges explicit `memory_candidates` from session logs (no LLM inside scripts).
- No cross-repo sync with image-scoring-gallery.

## Related

- [AGENTS.md](../../AGENTS.md) — slash command index
- [.agent/SAFETY.md](../../.agent/SAFETY.md) — secrets hygiene for memory writes
