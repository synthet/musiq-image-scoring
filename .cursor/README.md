# Cursor agent setup — image-scoring-backend

Project-local configuration for Cursor IDE agents. **Authority:** [AGENTS.md](../AGENTS.md), [.agent/AGENT_INFRA_INVENTORY.md](../.agent/AGENT_INFRA_INVENTORY.md).

## Layout

| Path | Role |
|------|------|
| [`rules/`](rules/) | Always-on or glob-scoped rules (`.mdc`). Canonical; mirror selected rules to [`.claude/rules/`](../.claude/rules/) in the same PR. |
| [`commands/`](commands/) | Slash commands (`/spec`, `/plan`, `/implement`, `/pr-ready`, `/task-claim`, wiki commands, external review, …). Mirror to [`.claude/commands/`](../.claude/commands/) when paired. |
| [`skills/`](skills/) | **Canonical** project skills (AST10). Mirror listed skills to [`.claude/skills/`](../.claude/skills/) byte-for-byte. |
| [`agents/`](agents/) | Subagent role definitions. Mirror to [`.claude/agents/`](../.claude/agents/). |
| [`plans/`](plans/) | Ephemeral Cursor plan artifacts — not source of truth; see [plans/README.md](plans/README.md). |
| [`mcp.example.json`](mcp.example.json) | **Template** — copy to gitignored [`mcp.json`](mcp.json). |
| [`mcp.pair.example.json`](mcp.pair.example.json) | Multi-root hint (backend + gallery keys). |

## MCP setup

1. Copy **`mcp.example.json`** → **`.cursor/mcp.json`** (or merge from `mcp.pair.example.json` in multi-root).
2. Attach **`is-be-mcp`** (stdio) for **`search`** + **`dispatch`**.
3. Optional **`is-be-webui`** (SSE) when WebUI is running — `execute_code` when `ENABLE_MCP_EXECUTE_CODE=1`.

Legacy profile servers (`is-be-diag`, `is-be-jobs`, `is-be-data`, `is-be-router`, `is-be-full`) are **not** in the default config. Use compact dispatch or run `scripts/batch/run_mcp_server_windows.bat` with `MCP_TOOL_PROFILE` for debug-only stdio profiles.

User **`~/.cursor/mcp.json`**: **`github`**, **`subagent-orchestrator`**, etc. only — see [`mcp.user.example.json`](mcp.user.example.json). Optional **`fff-be`** / **`fff-gallery`** are **project-level** in each repo's `.cursor/mcp.json` — see [AGENTS.md § fff](../AGENTS.md).

## Also use

- [`.agent/workflows/`](../.agent/workflows/) — step-by-step runbooks (WebUI, tests, MCP triage, cross-repo).
- [`.agent/skills/`](../.agent/skills/) — loader-only skills (e.g. `scoring-pipeline`, `image-scoring-mcp`); not mirrored to Claude.
- [`.agent/COMMANDS.md`](../.agent/COMMANDS.md) — verified shell commands (WSL venv, pytest, doctor).

## Slash commands (this repo)

| Command | Purpose |
|---------|---------|
| `/spec` | Feature/change spec with acceptance criteria |
| `/clarify` | Resolve material ambiguities before `/plan` |
| `/plan` | Implementation plan (after spec or small task) |
| `/tasks` | Traceable `T-n` task list from plan |
| `/analyze` | Cross-artifact coverage check before `/implement` |
| `/implement` | Execute approved plan |
| `/test-and-fix` | Run tests, fix failures |
| `/pr-ready` | Merge-ready summary + PR body |
| `/task-claim` | Claim GitHub Project board issue |
| `/release`, `/release-notes` | Semver release (backend) |
| `/backup-db` | Postgres backup workflow |
| `/windows-keep-awake on`, `/windows-keep-awake off` | Detached Windows sleep/display lock |
| `/critical-commit-audit` | High-severity post-commit review |
| `/wiki-ingest`, `/wiki-lint`, `/wiki-query` | Docs wiki maintenance |
| `/log-session`, `/dream-memory`, `/promote-memory`, `/memory-context` | Agent memory log → consolidate → promote |
| `/check-subagents`, `/run-*-review` | External Codex/Gemini review (MCP) |

## Drift checklist (maintainers)

1. MCP tool count in AGENTS.md matches `@mcp.tool` in `modules/mcp_server.py` — regenerate via `scripts/generate_mcp_tool_inventory.py`.
2. Skills with Claude mirror stay in sync — run `python scripts/sync_assistant_trees.py` after editing `.cursor/` assets (see [.agent/SKILL_INVENTORY.md](../.agent/SKILL_INVENTORY.md)).
3. CI gate: `python scripts/sync_assistant_trees.py --check` (also in `.github/workflows/agent-infra.yml`).
4. Wiki slash commands exist in both `.cursor/commands/` and `.claude/commands/`.
5. Bump [.agent/AGENT_INFRA_STATUS.json](../.agent/AGENT_INFRA_STATUS.json) `review_date` after infra passes.

See [docs/ai-workflow/README.md](../docs/ai-workflow/README.md) for the SDLC loop and phase gates.
