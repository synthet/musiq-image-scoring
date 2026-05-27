# Agent skill inventory (AST09)

Central list of **first-party** `SKILL.md` files in this repository for governance and periodic review. Aligns with [OWASP Agentic Skills Top 10 — AST09](https://github.com/kenhuangus/agentic-skills-top-10#ast09--no-governance).

**Upstream checklist:** [agentic-skills-top-10/checklist.md](https://github.com/kenhuangus/agentic-skills-top-10/blob/main/checklist.md)

**How to use:** When adding or materially changing a skill, update the **Last reviewed** date and ensure the **Canonical path** row matches [AGENTS.md](../AGENTS.md#agent-skills-source-of-truth-ast10).

## Risk tier (informal, for reviewers)

| Tier | Meaning |
|------|--------|
| **L1** | Read-only or narrow guidance; no destructive defaults |
| **L2** | Instructs shell/WSL, MCP, DB, or git push — high agency; trust repo review |

## Cursor project skills (canonical)

| Skill `name` | Path | Purpose (short) | Risk | Mirror under `.claude/skills/` | Last reviewed |
|--------------|------|-----------------|------|-------------------------------|---------------|
| backlog-queue | `.cursor/skills/backlog-queue/SKILL.md` | Cross-repo GitHub Project board contract (claim, transition, file) | L1 | Yes | 2026-04-28 |
| backup-db | `.cursor/skills/backup-db/SKILL.md` | Postgres backup workflow | L2 | — (Cursor only) | 2026-04-25 |
| commit-conventions | `.cursor/skills/commit-conventions/SKILL.md` | Conventional Commits / PR titles | L1 | Yes | 2026-04-25 |
| critical-commit-audit | `.cursor/skills/critical-commit-audit/SKILL.md` | High-severity post-commit review; trace paths, PR bar | L2 | Yes | 2026-04-26 |
| imgscore-backend-implementer | `.cursor/skills/imgscore-backend-implementer/SKILL.md` | Scoped backend implementation | L1 | Yes | 2026-04-25 |
| imgscore-mcp-debug | `.cursor/skills/imgscore-mcp-debug/SKILL.md` | MCP read-only triage | L2 | Yes | 2026-04-25 |
| mcp-debugging-workflow | `.cursor/skills/mcp-debugging-workflow/SKILL.md` | MCP debugging workflow | L2 | Yes | 2026-04-25 |
| security-review | `.cursor/skills/security-review/SKILL.md` | Pre-merge security sanity | L1 | Yes | 2026-04-25 |
| wsl-tf-python-runner | `.cursor/skills/wsl-tf-python-runner/SKILL.md` | WSL / venv / pytest commands | L2 | Yes | 2026-04-25 |
| subagent-review | `.cursor/skills/subagent-review/SKILL.md` | External Codex/Gemini review via subagent-orchestrator MCP | L2 | Yes | 2026-05-26 |

## Claude Code mirror

Skills listed with **Mirror = Yes** must stay in sync with **`.cursor/skills/<name>/SKILL.md`** (see [AGENTS.md](../AGENTS.md#agent-skills-source-of-truth-ast10)).

## `.agent/skills/` (Cursor; not mirrored to `.claude/skills/`)

| Skill `name` | Path | Purpose (short) | Risk | Last reviewed |
|--------------|------|-----------------|------|---------------|
| backlog-queue | `.agent/skills/backlog-queue/SKILL.md` | Project board contract (Antigravity / generic agent mirror of canonical Cursor skill) | L1 | 2026-04-28 |
| git-changelog | `.agent/skills/git-changelog/SKILL.md` | Git / changelog conventions | L1 | 2026-04-25 |
| image-scoring-mcp | `.agent/skills/image-scoring-mcp/SKILL.md` | MCP tools reference | L2 | 2026-04-25 |
| scoring-pipeline | `.agent/skills/scoring-pipeline/SKILL.md` | Pipeline architecture | L1 | 2026-04-25 |
| webui-dev | `.agent/skills/webui-dev/SKILL.md` | WebUI dev workflow | L1 | 2026-04-25 |
| webui-gradio | `.agent/skills/webui-gradio/SKILL.md` | Gradio UI architecture | L1 | 2026-04-25 |

## Subagents (Cursor / Claude Code)

Project subagents live under **`.cursor/agents/`** (canonical) and are mirrored to **`.claude/agents/`** for Claude Code parity. Same risk-tier convention as skills.

| Subagent `name` | Path | Purpose (short) | Risk | Claude mirror | Last reviewed |
|-----------------|------|-----------------|------|---------------|---------------|
| imgscore-backend-implementer | `.cursor/agents/imgscore-backend-implementer.md` | Scoped backend implementation, minimal diff | L2 | Yes | 2026-05-15 |
| imgscore-mcp-debug | `.cursor/agents/imgscore-mcp-debug.md` | Read-only MCP triage (53-tool surface) | L1 | Yes | 2026-05-15 |
| critical-commit-audit | `.cursor/agents/critical-commit-audit.md` | High-severity post-commit bug hunt | L2 | Yes | 2026-05-15 |
| pr-ready-hygiene | `.cursor/agents/pr-ready-hygiene.md` | Scoped lint/tests; PR-ready checklist | L2 | Yes | 2026-05-15 |
| wsl-tf-python-runner | `.cursor/agents/wsl-tf-python-runner.md` | WSL / venv / pytest marker resolution | L2 | Yes | 2026-05-15 |
| external-codex-review | `.cursor/agents/external-codex-review.md` | Codex-only external CLI review (MCP) | L2 | Yes | 2026-05-26 |
| external-gemini-review | `.cursor/agents/external-gemini-review.md` | Gemini-only external CLI review (MCP) | L2 | Yes | 2026-05-26 |
| external-cli-reviewer | `.cursor/agents/external-cli-reviewer.md` | Detect + run + panel-style external reviews | L2 | Yes | 2026-05-26 |

## Related repository

**image-scoring-gallery** maintains its own inventory: [../image-scoring-gallery/.agent/SKILL_INVENTORY.md](../image-scoring-gallery/.agent/SKILL_INVENTORY.md) when both repos are sibling checkouts.
