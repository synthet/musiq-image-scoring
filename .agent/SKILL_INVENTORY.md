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
| agent-memory | `.cursor/skills/agent-memory/SKILL.md` | Log/dream/promote + transcript import v2 | L2 | Yes | 2026-06-17 |
| backlog-queue | `.cursor/skills/backlog-queue/SKILL.md` | Cross-repo GitHub Project board contract (claim, transition, file) | L1 | Yes | 2026-04-28 |
| backlog-housekeeping | `.cursor/skills/backlog-housekeeping/SKILL.md` | GitHub Project board hygiene | L2 | Yes | 2026-06-16 |
| image-scoring-mcp | `.cursor/skills/image-scoring-mcp/SKILL.md` | Compact MCP search/dispatch | L2 | — (Cursor only) | 2026-05-31 |
| backup-db | `.cursor/skills/backup-db/SKILL.md` | Postgres backup workflow | L2 | — (Cursor only) | 2026-04-25 |
| commit-conventions | `.cursor/skills/commit-conventions/SKILL.md` | Conventional Commits / PR titles | L1 | Yes | 2026-04-25 |
| critical-commit-audit | `.cursor/skills/critical-commit-audit/SKILL.md` | High-severity post-commit review; trace paths, PR bar | L2 | Yes | 2026-04-26 |
| imgscore-backend-implementer | `.cursor/skills/imgscore-backend-implementer/SKILL.md` | Scoped backend implementation | L1 | Yes | 2026-04-25 |
| backend-frontend-ui | `.cursor/skills/backend-frontend-ui/SKILL.md` | React `/ui/` SPA, design tokens, Gradio CSS sync | L1 | Yes | 2026-06-21 |
| imgscore-mcp-debug | `.cursor/skills/imgscore-mcp-debug/SKILL.md` | MCP read-only triage | L2 | Yes | 2026-04-25 |
| mcp-debugging-workflow | `.cursor/skills/mcp-debugging-workflow/SKILL.md` | MCP debugging workflow | L2 | Yes | 2026-04-25 |
| security-review | `.cursor/skills/security-review/SKILL.md` | Pre-merge security sanity | L1 | Yes | 2026-04-25 |
| wsl-tf-python-runner | `.cursor/skills/wsl-tf-python-runner/SKILL.md` | WSL / venv / pytest commands | L2 | Yes | 2026-04-25 |
| wsl-environment | `.cursor/skills/wsl-environment/SKILL.md` | WSL2 lifecycle — venv provision, long GPU jobs, recovery, disk | L2 | Yes | 2026-05-30 |
| windows-keep-awake | `.cursor/skills/windows-keep-awake/SKILL.md` | Detached Windows sleep/display lock via SetThreadExecutionState | L2 | — (Cursor only) | 2026-06-21 |
| docs-wiki | `.cursor/skills/docs-wiki/SKILL.md` | Backend docs wiki maintenance | L1 | — (Cursor only; `.agent/skills/docs-wiki` is thin alias) | 2026-05-31 |
| subagent-review | `.cursor/skills/subagent-review/SKILL.md` | External Codex/Gemini review via subagent-orchestrator MCP | L2 | Yes | 2026-05-26 |
| codebase-size-audit | `.cursor/skills/codebase-size-audit/SKILL.md` | Large-file / long-method read-only audit script + report | L1 | Yes | 2026-06-30 |
| validate-implementation | `.cursor/skills/validate-implementation/SKILL.md` | Per-AC gate via compiled harness `scripts/agent_skills/validate_implementation.py` | L1 | Yes | 2026-07-19 |
| release-bump | `.cursor/skills/release-bump/SKILL.md` | Semver + changelog via compiled harness `scripts/agent_skills/release_bump.py` | L1 | Yes | 2026-07-19 |
| threat-modeling-agentic-tools | `.cursor/skills/threat-modeling-agentic-tools/SKILL.md` | MCP/hook/prompt-injection threat modeling | L1 | Yes | 2026-07-01 |
| mcp-server-design | `.cursor/skills/mcp-server-design/SKILL.md` | Safe MCP server design patterns | L1 | Yes | 2026-07-01 |
| eval | `.cursor/skills/eval/SKILL.md` | Task quality signals → agent memory feedback loop | L1 | Yes | 2026-07-01 |
| agent-cli-hub | `.cursor/skills/agent-cli-hub/SKILL.md` | CLI skill router; install tiers, agent-environment, shared references | L1 | Yes | 2026-07-04 |
| agent-search | `.cursor/skills/agent-search/SKILL.md` | rg/grep/ast-grep/fd tool selection + fff when connected | L1 | Yes | 2026-07-04 |
| agent-git-workflows | `.cursor/skills/agent-git-workflows/SKILL.md` | git/gh safe status, diff, PR workflows | L2 | Yes | 2026-07-04 |
| agent-data-config | `.cursor/skills/agent-data-config/SKILL.md` | jq/yq/curl config and API inspection | L1 | Yes | 2026-07-04 |
| agent-dev-tooling | `.cursor/skills/agent-dev-tooling/SKILL.md` | WSL pytest, ruff, doctor, docker compose | L1 | Yes | 2026-07-04 |
| agent-platform-tooling | `.cursor/skills/agent-platform-tooling/SKILL.md` | Windows vs WSL2 environment choice | L1 | Yes | 2026-07-04 |
| mcp-code-intelligence | `.cursor/skills/mcp-code-intelligence/SKILL.md` | MCP vs CLI tiers; fff + is-be-mcp | L1 | Yes | 2026-07-04 |

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
| docs-wiki | `.agent/skills/docs-wiki/SKILL.md` | Alias → `.cursor/skills/docs-wiki` | L1 | 2026-05-31 |

## Subagents (Cursor / Claude Code)

Project subagents live under **`.cursor/agents/`** (canonical) and are mirrored to **`.claude/agents/`** for Claude Code parity. Same risk-tier convention as skills.

| Subagent `name` | Path | Purpose (short) | Risk | Claude mirror | Last reviewed |
|-----------------|------|-----------------|------|---------------|---------------|
| imgscore-backend-implementer | `.cursor/agents/imgscore-backend-implementer.md` | Scoped backend implementation, minimal diff | L2 | Yes | 2026-05-15 |
| imgscore-mcp-debug | `.cursor/agents/imgscore-mcp-debug.md` | Read-only MCP triage | L1 | Yes | 2026-05-31 |
| critical-commit-audit | `.cursor/agents/critical-commit-audit.md` | High-severity post-commit bug hunt | L2 | Yes | 2026-05-15 |
| pr-ready-hygiene | `.cursor/agents/pr-ready-hygiene.md` | Scoped lint/tests; PR-ready checklist | L2 | Yes | 2026-05-15 |
| wsl-tf-python-runner | `.cursor/agents/wsl-tf-python-runner.md` | WSL / venv / pytest marker resolution | L2 | Yes | 2026-05-15 |
| wsl-environment | `.cursor/agents/wsl-environment.md` | WSL2 lifecycle — provision, detached jobs, recovery | L2 | Yes | 2026-05-30 |
| external-codex-review | `.cursor/agents/external-codex-review.md` | Codex-only external CLI review (MCP) | L2 | Yes | 2026-05-26 |
| external-gemini-review | `.cursor/agents/external-gemini-review.md` | Gemini-only external CLI review (MCP) | L2 | Yes | 2026-05-26 |
| external-cli-reviewer | `.cursor/agents/external-cli-reviewer.md` | Detect + run + panel-style external reviews | L2 | Yes | 2026-05-26 |

## Related repository

**image-scoring-gallery** maintains its own inventory: [../image-scoring-gallery/.agent/SKILL_INVENTORY.md](../image-scoring-gallery/.agent/SKILL_INVENTORY.md) when both repos are sibling checkouts.
