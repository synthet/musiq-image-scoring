---
name: mcp-debugging-workflow
description: Use image-scoring MCP tools to debug scoring failures, check database health, and investigate system issues. Trigger when the user asks to debug scoring, investigate failure, or check database health.
---

# MCP Debugging Workflow

## When to Use

Apply this skill when the user asks to:
- Debug scoring
- Investigate failure
- Check database health
- Find failed images
- Diagnose pipeline issues

## Workflow Steps

### 1. Get Error Overview

On **`is-be-mcp`**: `search("scoring failures")` → `dispatch("diagnostics.get_error_summary", {})`.

### 2. Check Database Health

`dispatch("diagnostics.check_database_health", {})`

### 3. Get Failed Images (if errors found)

`dispatch("jobs.get_failed_images", {"limit": 50})`

### 4. Check Model/GPU Status

`dispatch("diagnostics.get_model_status", {})`

### 5. Check Active Jobs (if processing expected)

On **`is-be-mcp`**: `dispatch("jobs.get_runner_status", {})` and/or `dispatch("jobs.get_recent_jobs", {})`. If `search` finds no matching action, use optional **`is-be-live`** with **`MCP_SSE_PROFILE=full`** for legacy raw tools.

### 6. Read Debug Log (for detailed errors)

`dispatch("logs.read_debug_log", {"lines": 100})` or `dispatch("logs.search_logs", {"pattern": "error|failed"})`

## Server Selection

- **Default:** **`is-be-mcp`** → **`search`** / **`dispatch`**
- **Optional SSE:** **`is-be-live`** (same compact tools when WebUI is running)
- **`execute_code` / full legacy raw tools:** **`is-be-live`** + `MCP_SSE_PROFILE=full` + `ENABLE_MCP_EXECUTE_CODE=1` when needed

## Terminology

Align with product UI: pipeline stages are **Discovery → Inspection → Quality Analysis → Similarity Clustering → Tagging**; DB uses `phase_code`; REST uses `scoring` / `tagging` / `clustering`. See **[docs/technical/PIPELINE_TERMINOLOGY.md](../../../docs/technical/PIPELINE_TERMINOLOGY.md)**.

## References

- [AGENTS.md](../../../AGENTS.md) — Common Workflows, Quick Decision Tree
- [.agent/mcp_tools_reference.md](../../../.agent/mcp_tools_reference.md) — Tool parameters
- [.cursor/rules/image-scoring-mcp.mdc](../../rules/image-scoring-mcp.mdc)
