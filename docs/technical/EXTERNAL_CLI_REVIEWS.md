# External CLI reviews (subagent-orchestrator)

Optional **review-only** second opinions from **Codex** or **Gemini CLI**, orchestrated locally via the sibling [`subagent-orchestrator`](../../subagent-orchestrator) package. Cursor remains the primary editor.

## Prerequisites

1. Sibling checkout: `../subagent-orchestrator` next to this repo (same parent as `image-scoring-gallery`).
2. Build once:

   ```bash
   cd ../subagent-orchestrator/agent-orchestrator
   npm install && npm run build
   ```

3. Install and authenticate **codex** and/or **gemini** CLIs on your PATH (see orchestrator `detect_subagents` notes).
4. Reload MCP in Cursor after changing [`.cursor/mcp.json`](../../.cursor/mcp.json).

## MCP in this repo

| Key | Purpose |
|-----|---------|
| `imgscore-subagent-orchestrator` | `detect_subagents`, `run_subagent` (review-only) |

`WORKSPACE_ROOT` is this repository; run outputs are written under **`.agent-runs/`** (gitignored).

## Slash commands

| Command | Use |
|---------|-----|
| `/check-subagents` | See which CLIs are available |
| `/run-codex-review` | Single Codex review |
| `/run-gemini-review` | Single Gemini review |
| `/run-subagent-review` | Auto-select, or `codex` / `gemini` / `both` prefix |

Skill: [`.cursor/skills/subagent-review/SKILL.md`](../../.cursor/skills/subagent-review/SKILL.md). Rule: [`.cursor/rules/external-cli-subagents.mdc`](../../.cursor/rules/external-cli-subagents.mdc).

## Safety

- v0.1 is **review-only** — `allowWrites: true` is rejected.
- Do not pass secrets, `.env`, or full `config.json` in prompts.
- Code you attach may be sent to external providers; see [.agent/SAFETY.md](../../.agent/SAFETY.md).

## Cross-repo

Changes spanning **backend** and **gallery** need **separate** reviews per workspace (open each repo and run MCP there). v0.1 cannot review both roots in one call.

## Upstream docs

- [subagent-orchestrator README](https://github.com/synthet/subagent-orchestrator) (local: `../subagent-orchestrator/README.md`)
- [agent-orchestrator/README.md](../../subagent-orchestrator/agent-orchestrator/README.md)
