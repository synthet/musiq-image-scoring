# Subagents and logical roles — image-scoring-backend

Physical definitions live in [`.cursor/agents/`](../.cursor/agents/) (mirrored to [`.claude/agents/`](../.claude/agents/) for Claude Code). This file maps **logical role names** (for planning) to those files and primary skills.

## Role matrix

| Logical role | Concrete subagent / skill | Responsibility | Canonical sources |
|--------------|---------------------------|----------------|-------------------|
| backend-diagnostics-agent | [`imgscore-mcp-debug`](../.cursor/agents/imgscore-mcp-debug.md), [`imgscore-mcp` skill](skills/image-scoring-mcp/SKILL.md) | Read-only MCP triage, logs, DB health | [docs/DIAGNOSTICS.md](../docs/DIAGNOSTICS.md), [AGENTS.md](../AGENTS.md) |
| api-contract-agent | Manual + [`imgscore-backend-implementer`](../.cursor/agents/imgscore-backend-implementer.md) | REST shapes, OpenAPI sync | [docs/technical/API_CONTRACT.md](../docs/technical/API_CONTRACT.md), [docs/reference/api/openapi.yaml](../docs/reference/api/openapi.yaml) |
| db-schema-agent | `imgscore-backend-implementer` | Alembic, `db_postgres`, DB_SCHEMA | [docs/technical/DB_SCHEMA.md](../docs/technical/DB_SCHEMA.md), `migrations/versions/` |
| pipeline-runner-agent | `imgscore-backend-implementer`, [scoring-pipeline skill](skills/scoring-pipeline/SKILL.md) | Phases, jobs, runners | [docs/IMAGE_PIPELINE.md](../docs/IMAGE_PIPELINE.md), [PIPELINE_TERMINOLOGY.md](../docs/technical/PIPELINE_TERMINOLOGY.md) |
| scoring-model-agent | `imgscore-backend-implementer` | ML models, scoring modules | Code in `modules/scoring.py`, model docs in `docs/` |
| docs-wiki-agent | [.agent/skills/docs-wiki/SKILL.md](skills/docs-wiki/SKILL.md) | Wiki structure, log.md | [docs/WIKI_SCHEMA.md](../docs/WIKI_SCHEMA.md), [documentation.mdc](../.cursor/rules/documentation.mdc) |
| mcp-safety-agent | N/A (policy) | Safe MCP profiles, deny writes | [workflows/safe_mcp_diagnostics.md](workflows/safe_mcp_diagnostics.md), [SAFETY.md](SAFETY.md) |
| test-stabilization-agent | [`pr-ready-hygiene`](../.cursor/agents/pr-ready-hygiene.md), [`wsl-tf-python-runner`](../.cursor/agents/wsl-tf-python-runner.md) | Pytest markers, venv, CI hygiene | [docs/TESTING.md](../docs/TESTING.md), [AGENTS.md](../AGENTS.md) |
| external-review-agent | [`external-cli-reviewer`](../.cursor/agents/external-cli-reviewer.md), [`subagent-review`](../.cursor/skills/subagent-review/SKILL.md) | Review-only Codex/Gemini via MCP; tie-breaker / panel | [docs/technical/EXTERNAL_CLI_REVIEWS.md](../docs/technical/EXTERNAL_CLI_REVIEWS.md) |

## Allowed vs forbidden edits (defaults)

| Role | Allowed | Forbidden |
|------|---------|-----------|
| Diagnostics / mcp-debug | Read-only tool calls, SELECT SQL, log inspection | `run_processing_job`, `prune_missing_files`, `set_config_value`, … without explicit user request |
| Implementer | Targeted code in `modules/`, `migrations/`, `tests/` | Gallery/Electron code; breaking API without coordinated change |
| PR-ready hygiene | Lint/tests on changed paths | Disabling tests; clearing entire repo lint debt |
| Critical audit | Minimal fix + test when bug proven | Speculative refactors |
| External review | MCP `run_subagent` with `allowWrites: false`; read `.agent-runs/` | Auto-apply patches; `allowWrites: true`; raw `codex`/`gemini` shell unless user bypasses |

## Validation commands (after implementation roles touch code)

- `ruff check` on touched Python files
- Narrowest `pytest` covering the path; fast gate: `python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py`

## Handoff notes

- **Cross-repo API/schema:** use [workflows/cross_repo_contract_change.md](workflows/cross_repo_contract_change.md); gallery work continues in **image-scoring-gallery** after backend canonical docs Updated.
- **Deep gallery UI:** hand off to sibling repo [`gallery-electron-ts`](https://github.com/synthet/image-scoring-gallery/blob/main/.cursor/agents/gallery-electron-ts.md) agent.
