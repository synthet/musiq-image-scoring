---
name: agent-cli-hub
description: >-
  Choose CLI tools and safe patterns before repo work. Install checklist,
  bounded search/read commands, and confirmation gates. Use when navigating
  the codebase, running shell commands, or setting up agent tooling on
  Windows, WSL2, or macOS.
---

# Agent CLI hub

Router for lightweight CLI tooling skills in **image-scoring-backend** (Vexlum Scoring). Prefer bounded, low-memory commands before broad reads or heavyweight indexers.

## Purpose

Central entry point for agent-safe CLI workflows: which skill to use, how to install tools, how to bound output, and when to ask for confirmation.

## When to use

- Starting work in an unfamiliar repo or shell environment
- Choosing between text search, structural search, git, config tools, or MCP layers
- Before running install commands or destructive shell operations

## Skill router

| Need | Skill |
|------|-------|
| Find files / grep / browse tree | [`agent-search`](../agent-search/SKILL.md) — rg vs grep vs ast-grep vs fd; prefer **fff** MCP when installed |
| git status, diff, gh PR/issue | [`agent-git-workflows`](../agent-git-workflows/SKILL.md) |
| jq/yq on JSON/YAML, API probes | [`agent-data-config`](../agent-data-config/SKILL.md) |
| pytest, ruff, doctor, docker compose | [`agent-dev-tooling`](../agent-dev-tooling/SKILL.md) |
| Windows vs WSL2 choice | [`agent-platform-tooling`](../agent-platform-tooling/SKILL.md) |
| MCP vs CLI code intelligence | [`mcp-code-intelligence`](../mcp-code-intelligence/SKILL.md) |
| Pipeline / DB triage via MCP | [`image-scoring-mcp`](../image-scoring-mcp/SKILL.md) |
| WSL venv / pytest markers | [`wsl-tf-python-runner`](../wsl-tf-python-runner/SKILL.md) |
| Fast indexed file search (MCP) | **[fff](https://github.com/dmtrKovalenko/fff)** — user-level `fff-mcp`; see [mcp.user.example.json](../../../.cursor/mcp.user.example.json) |

## Required tools (baseline)

`git`, `rg`, `fd`, `jq`, Python (WSL + venv). Install full set via [references/install-blocks.md](references/install-blocks.md).

## Install

See [references/install-blocks.md](references/install-blocks.md) — Windows winget, WSL2 apt, macOS Homebrew.

## Agent-safe patterns

1. Inspect `git status --short` before editing.
2. Use bounded output — see [references/bounded-output-patterns.md](references/bounded-output-patterns.md).
3. Prefer documented commands from [AGENTS.md](../../../AGENTS.md) and [`.agent/COMMANDS.md`](../../../.agent/COMMANDS.md).
4. Do not assume repo language before inspecting `requirements.txt`, `pyproject.toml`, etc.
5. Never auto-run destructive commands — see [references/commands-requiring-confirmation.md](references/commands-requiring-confirmation.md).

## Commands requiring confirmation

Full list: [references/commands-requiring-confirmation.md](references/commands-requiring-confirmation.md).

## Platform guidance

[references/windows-wsl-split.md](references/windows-wsl-split.md) — WSL2 for Python/pytest/GPU; Windows for gh and light search.

## Troubleshooting

- **Tool not found:** Re-run install block for your platform; restart shell.
- **Slow search on WSL:** Avoid `/mnt/c` for heavy repos; clone under `~/src`.
- **Backend health:** `python scripts/doctor.py --no-gpu` in WSL + `~/.venvs/tf`.

## Verification checklist

```bash
git --version && rg --version && jq --version
python scripts/doctor.py --no-gpu   # WSL + tf venv — backend-specific
```
