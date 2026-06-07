---
description: Use subagent-orchestrator MCP for external CLI reviews; review-only, no secrets, no raw codex/gemini shell by default.
alwaysApply: true
---

# External CLI sub-agents

External CLI agents (Codex, Gemini, Claude) are **review and tie-breaker** tools. **Cursor remains the primary editor.**

## How to invoke

- Use MCP server **subagent-orchestrator** tools only:
  - `detect_subagents` — check availability first
  - `run_subagent` — run one review
- Project MCP key (if configured): **`cli-review`** (`../subagent-orchestrator/agent-orchestrator/dist/index.js`). Cursor may also merge user-level **`subagent-orchestrator`**; confirm via `SERVER_METADATA.json` (`serverName`: `subagent-orchestrator`).
- Read tool schemas under `mcps/*/tools/` before calling.

## Do not

- Run `codex exec`, `gemini -p`, or `claude -p` in the integrated terminal **unless the user explicitly asks to bypass the orchestrator**.
- Set `allowWrites: true` on `run_subagent` (rejected in v0.1).
- Pass API keys, tokens, or `.env` content in `task` or `extraContext`.
- Auto-apply patches from external agent output without user approval.

## Workflow

1. `detect_subagents` before the first live run in a session.
2. Prefer `dryRun: true` when validating setup.
3. `run_subagent` with `mode: "review"`, `allowWrites: false`, workspace-relative `files`.
4. Read `outputFile` under `.agent-runs/`; summarize with severity (blocker | high | medium | low | nit).

## Claude

Claude may appear in detection but **execution is stubbed in v0.1** — use Codex or Gemini for live reviews.

## image-scoring-backend

- Never pass `secrets.json`, `.env`, or full `config.json` contents in `task` or `extraContext`.
- Do not include large binaries, model weights, `FirebirdLinux/`, or personal image libraries in `files`.
- External review complements `/pr-ready` and `/critical-commit-audit` — it does not replace them.

## Related

- Skill: `subagent-review`
- Commands: `/check-subagents`, `/run-codex-review`, `/run-gemini-review`, `/run-subagent-review`
- Setup: [docs/technical/EXTERNAL_CLI_REVIEWS.md](../../docs/technical/EXTERNAL_CLI_REVIEWS.md)
- Index: [AGENTS.md](../../AGENTS.md)
