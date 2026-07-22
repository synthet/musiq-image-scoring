---
type: Documentation Hub
title: AI Workflow & Asset Map
description: Where every agent asset lives (rules, commands, skills, agents, memory, workflows) and the SDLC loop they support.
resource: ai-workflow/README.md
tags: [docs, agents, workflow]
timestamp: 2026-07-21T00:00:00Z
okf_version: 0.1
---

# AI workflow & asset map

## Where agent assets live

| Asset | Location | Notes |
|-------|----------|-------|
| Cursor commands | `.cursor/commands/*.md` | **Canonical** authoring source |
| Cursor skills | `.cursor/skills/*/SKILL.md` | **Canonical** authoring source |
| Cursor subagents | `.cursor/agents/*.md` | **Canonical** authoring source |
| Cursor rules | `.cursor/rules/*.mdc` | Always-on or glob-scoped guidance |
| Claude mirror | `.claude/{rules,commands,skills,agents}` | **Generated** from `.cursor/` for listed assets — run sync script |
| MCP template | `.cursor/mcp.example.json` | Copy to gitignored `.cursor/mcp.json` to attach servers |
| Agent governance | `.agent/` | Safety, inventory, subagent role matrix, workflow playbooks |
| Project memory | `.agent-memory/` | log → dream → promote (see `CURSOR_USAGE.md`) |
| Workflow playbooks | `.agent/workflows/*.md` | spec / plan / implement / pr-ready / test-and-fix / … |

**Single source of truth:** edit assets under **`.cursor/`** + **`.agent/`**, then run
`python scripts/sync_assistant_trees.py` to regenerate the `.claude/` mirror.

**Upstream:** Generic patterns originate from [synthet-code-framework](https://github.com/synthet/synthet-code-framework); this repo is a domain fork (see **AGENTS.md**). Framework ships a **flat 13-skill** CLI layout; this backend uses the **consolidated hub** (7 skills) aligned with sibling gallery — see [`.agent/cli-tools-skills-spec.md`](../../.agent/cli-tools-skills-spec.md).

### Skill clusters

| Cluster | Skills | When |
|---------|--------|------|
| **SDLC / governance** | `backlog-queue`, `validate-implementation`, `commit-conventions`, `eval`, `karpathy-guidelines`, `systematic-debugging`, `test-driven-development`, `verification-before-completion`, … | Every task, PR, spec |
| **Domain (backend)** | `image-scoring-mcp`, `wsl-tf-python-runner`, `wsl-environment`, `imgscore-*`, … | Pipeline, WSL, MCP triage |
| **Generic CLI** | `agent-cli-hub` → `agent-search`, `agent-git-workflows`, `agent-data-config`, `agent-dev-tooling`, `agent-platform-tooling`, `mcp-code-intelligence` | Shell navigation, git, pytest/ruff, Windows/WSL |

Start generic CLI work at **`agent-cli-hub`**. Validate: `python scripts/validate_cli_hub_skills.py`.

## Framework alignment

Upstream: [synthet-code-framework](https://github.com/synthet/synthet-code-framework) (generic agent scaffold). This repo is a **Cursor-first domain fork** — see [framework-adoption-port-manifest](../raw/framework-adoption-port-manifest.md).

| Framework pattern | This repo |
|-------------------|-----------|
| Single SOT + mirror | `.cursor/` canonical → `.claude/` via `sync_assistant_trees.py` |
| CLI tooling | 7-skill hub (not 13 flat skills) — content-equivalent map in port manifest |
| CI agent-infra | [`.github/workflows/agent-infra.yml`](../../.github/workflows/agent-infra.yml) |

```bash
python scripts/sync_assistant_trees.py --check
python scripts/validate_cli_hub_skills.py
python scripts/ci/check_agent_frontmatter.py
python scripts/ci/check_secrets.py
```

Cherry-pick generic improvements from framework; never blind-merge domain rules or MCP inventory.

## The SDLC loop

```
/spec → /clarify? → /plan → /tasks → /analyze? → /implement → /test-and-fix → validate-implementation → /pr-ready → (optional) /run-subagent-review → /release-notes
```

`/clarify`, `/tasks`, and `/analyze` are **required for non-trivial multi-AC work**; trivial fixes may skip them with an explicit note. See [`.agent/SPEC_KIT_ADOPTION.md`](../../.agent/SPEC_KIT_ADOPTION.md).

### Phase gates

Each phase produces an artifact that gates the next one. Do not skip a gate silently — if a phase
is unnecessary (trivial fix), say so explicitly.

| Phase | Artifact produced | Gate to pass before the next phase |
|-------|-------------------|-------------------------------------|
| `/spec` | Spec with EARS `AC-n` acceptance criteria | User approves; no criterion is AMBIGUOUS |
| `/clarify` | Clarification summary + spec patch notes (when needed) | Planning readiness Ready / Ready with assumptions |
| `/plan` | Implementation plan (files, approach, tests, rollback) | User approves the plan |
| `/tasks` | Traceable `T-n` task list mapped to `AC-n` | No orphaned ACs; verification paths listed |
| `/analyze` | Coverage / consistency matrix (non-trivial work) | Implementation readiness Ready (or warnings accepted) |
| `/implement` | Minimal-diff change set with tests | Lint + narrowest tests green |
| `/test-and-fix` | Green test run (or written blocker); RCA log entry for non-obvious failures | Tests pass or blocker documented |
| `validate-implementation` (skill) | Per-AC Verified/Failed/Unknown report with evidence | Every AC Verified, or open items accepted by the user |
| `/pr-ready` | Definition-of-done report + paste-ready PR text | Checks green, `Closes #<N>`, card in `Stage = Review` |

- **Backlog first:** pick and claim work via the [backlog contract](../project/00-backlog-workflow.md) (`/task-claim`).
- **Review:** `/critical-commit-audit` for high-severity bug hunts; `/check-subagents` +
  `/run-codex-review` / `/run-gemini-review` for external second opinions.
- **Docs:** `/wiki-ingest`, `/wiki-lint`, `/wiki-query` keep `docs/` healthy (see [WIKI_SCHEMA](../WIKI_SCHEMA.md)).
- **Memory:** `/log-session` → `/dream-memory` → `/promote-memory` → `/memory-context`.

## Safety

All of the above operate under [`.agent/SAFETY.md`](../../.agent/SAFETY.md) and the always-on **`safety-and-secrets`** rule.
