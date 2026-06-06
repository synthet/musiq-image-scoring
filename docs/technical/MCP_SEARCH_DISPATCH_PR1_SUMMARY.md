# MCP search + dispatch — PR1 work summary

**Date:** 2026-06-06  
**Design:** [planning/mcp-search-dispatch.md](../planning/mcp-search-dispatch.md)  
**Contract:** [MCP_SEARCH_DISPATCH.md](MCP_SEARCH_DISPATCH.md)

## Goal

Replace the “pick one of ~54 tools or run `be_find` first” agent experience with a **stable compact surface**: **`search(query)`** → **`dispatch(action_id, arguments)`** on a curated, CI-checked action registry. PR1 is **backend-only**, **read-only** actions.

## Architecture

```text
is-be-mcp (compact, stdio)
  ├── search   → BM25 over mcp/action_registry.json
  └── dispatch → registry → policy → handlers → mcp_server / doctor_cli

is-be-router (compat)
  ├── search, dispatch
  └── deprecated be_find, be_card, be_domains

is-be-diag | is-be-jobs | is-be-data | …
  └── legacy @mcp.tool names unchanged
```

## Locked decisions (PR1)

| Topic | Decision |
|-------|----------|
| Compact server | **`is-be-mcp`** exposes only `search` + `dispatch` |
| Curation | Manual overlay in `mcp/actions/overlay.yaml`; no OpenAPI auto-gen in PR1 |
| Gallery | Backend-only v1; gallery keeps **`is-ui-*`** / `ui_find` |
| `execute_sql` | Excluded from compact registry |
| Action IDs | Stable dotted IDs + integer **`version`** field (no `.v2` suffix) |

## New / changed code

### Registry & actions

| Path | Role |
|------|------|
| `mcp/action_registry.schema.json` | JSON Schema for registry entries |
| `mcp/actions/overlay.yaml` | Curated metadata, policy, handler refs (14 actions) |
| `mcp/action_registry.json` | Generated merged registry (CI-checked) |
| `modules/mcp/actions/registry.py` | Load / lookup actions |
| `modules/mcp/actions/search.py` | BM25 search over registry |
| `modules/mcp/actions/dispatch.py` | Validate, policy, invoke, envelope |
| `modules/mcp/actions/handlers.py` | Bridge to `mcp_server` + `doctor_cli` |
| `modules/mcp/actions/policy.py` | PR1: read-only only |
| `modules/mcp/actions/schema.py` | Argument validation |
| `modules/mcp/actions/envelope.py` | Normalized response shape |
| `modules/mcp/actions/errors.py` | Error codes |

### Router / profiles

| Path | Role |
|------|------|
| `modules/mcp/names.py` | `BE_MCP = "is-be-mcp"`, compact profile |
| `modules/mcp/profiles.py` | `compact` profile |
| `modules/mcp/router_tools.py` | `register_compact_tools()`, deprecated `be_*` |
| `modules/mcp/router_server.py` | `MCP_TOOL_PROFILE=compact` → `is-be-mcp` |
| `modules/mcp/bm25.py` | Extended fields: `action_id`, `title`, `aliases`, … |
| `scripts/batch/run_mcp_compact_windows.bat` | Windows launcher |
| `scripts/batch/run_mcp_compact_wsl.bat` | WSL launcher |

### Generator & CI

| Path | Role |
|------|------|
| `scripts/generate_mcp_tool_inventory.py` | `--update-action-registry`, `--check-action-registry` |
| `.github/workflows/mcp-tool-doc-sync.yml` | Validates registry sync |

### Tests (20 passed)

| File | Coverage |
|------|----------|
| `tests/test_mcp_action_registry.py` | Load, PR1 action set, schema/version |
| `tests/test_mcp_search.py` | Evaluation queries, filters, low_confidence |
| `tests/test_mcp_dispatch.py` | Envelope, validation, mocked handlers |
| `tests/test_mcp_tool_router.py` | Router/BM25 compat unchanged |

## PR1 dispatchable actions (14)

| action_id | Legacy tool | Notes |
|-----------|-------------|-------|
| `diagnostics.run_doctor` | *(CLI only)* | `{"no_gpu": true}` |
| `diagnostics.get_error_summary` | `get_error_summary` | |
| `diagnostics.check_database_health` | `check_database_health` | |
| `diagnostics.validate_config` | `validate_config` | |
| `diagnostics.get_database_engine_info` | `get_database_engine_info` | |
| `diagnostics.verify_environment` | `verify_environment` | |
| `diagnostics.get_model_status` | `get_model_status` | |
| `logs.read_debug_log` | `read_debug_log` | |
| `logs.get_server_log_tail` | `get_server_log_tail` | |
| `logs.search_logs` | `search_logs` | |
| `config.get_config` | `get_config` | |
| `jobs.get_failed_images` | `get_failed_images` | |
| `jobs.get_run_diagnostics` | `get_run_diagnostics` | requires `run_id` |
| `data.get_embedding_stats` | `get_embedding_stats` | |

**Excluded:** maintenance/write tools, `export_debug_bundle`, `execute_sql`, `execute_code`.

## MCP config

| File | Change |
|------|--------|
| `.cursor/mcp.json` | **`is-be-mcp`** added (preferred) |
| `.mcp.json` | **`is-be-mcp`** for Claude Code |
| `.cursor/mcp.pair.example.json` | **`is-be-mcp`** template |
| `.claude/settings.json` | `is-be-mcp` enabled; `search`/`dispatch` permissions |

## Documentation & agent infra

### Backend

- **New:** `docs/technical/MCP_SEARCH_DISPATCH.md` (canonical contract)
- **Updated:** `AGENTS.md`, `CANONICAL_SOURCES.md`, `DIAGNOSTICS.md`, `MCP_DEBUGGING_TOOLS.md`, `LLM_CONTEXT.md`, `AGENT_COORDINATION.md`, `CLAUDE.md`, `docs/log.md`
- **Planning:** §12 open questions → locked **Decisions** in `docs/planning/mcp-search-dispatch.md`
- **Skills:** `.agent/skills/image-scoring-mcp`, `.claude/skills/imgscore-mcp-debug`, `.claude/skills/mcp-debugging-workflow`
- **Cursor mirrors:** `.cursor/skills/{image-scoring-mcp,imgscore-mcp-debug,mcp-debugging-workflow}`
- **Rules:** `.cursor/rules/image-scoring-mcp.mdc`, `.claude/rules/image-scoring-mcp.mdc`, `.cursor/rules/mcp-schema-check.mdc`
- **Workflows:** `.agent/workflows/safe_mcp_diagnostics.md`, `debug_pipeline_run.md`
- **Reference:** `.agent/mcp_tools_reference.md`, `.agent/AGENT_INFRA_INVENTORY.md`, `.agent/SKILL_INVENTORY.md`
- **Stale names removed** from active agent docs (`imgscore-py-*`, `is-ga-*`, etc.)

### Gallery (cross-repo docs only)

- `AGENTS.md`, `.agent/skills/image-scoring-mcp/SKILL.md`, `.agent/mcp_tools_reference.md`, `.agent/workflows/debug_gallery_backend_connection.md` — backend triage via sibling **`is-be-mcp`**

## Agent workflow (new default)

```text
1. Attach is-be-mcp (stdio)
2. search("why did scoring fail")
3. dispatch("diagnostics.get_error_summary", {})
4. dispatch("jobs.get_failed_images", {"limit": 20})
```

Legacy: domain servers and **`is-be-router`** `be_find` remain for compatibility.

## Verification commands

```bash
# Regenerate registry (after overlay edits)
python scripts/generate_mcp_tool_inventory.py --update-action-registry

# CI check
python scripts/generate_mcp_tool_inventory.py --check-action-registry

# Tests (WSL ~/.venvs/tf)
pytest tests/test_mcp_action_registry.py tests/test_mcp_search.py \
       tests/test_mcp_dispatch.py tests/test_mcp_tool_router.py -v

# Stale vocabulary scan (expect zero hits on active docs)
rg -l 'imgscore-py-|is-ga-|ga_find|mcp__imgscore-py' \
  .agent .claude .cursor docs AGENTS.md CLAUDE.md \
  --glob '!CHANGELOG.md' --glob '!docs/archive/**' --glob '!notebooklm_docs.md'
```

## Out of scope (post-PR1)

- Gallery `search`/`dispatch` mirror
- OpenAPI draft action generation (`--draft-openapi-actions`)
- Write/maintenance actions in compact dispatch
- Elevated read-only tools (`execute_sql`) in registry
- Optional `scripts/lint_mcp_doc_vocabulary.py` CI lint
