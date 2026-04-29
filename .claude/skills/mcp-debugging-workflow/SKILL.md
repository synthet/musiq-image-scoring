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

Call `get_error_summary` (Vexlum Scoring MCP: **`imgscore-py-stdio`** in the Python workspace, **`imgscore-el-stdio`** in the Electron workspace) to identify scope of failures: failed jobs, missing scores, orphaned records.

### 2. Check Database Health

Call `check_database_health` to validate data integrity (orphaned records, duplicates, inconsistencies).

### 3. Get Failed Images (if errors found)

Call `get_failed_images` with optional `limit` to list images that need reprocessing.

### 4. Check Model/GPU Status

Call `get_model_status` to verify GPU availability, model loading, CUDA/PyTorch/TensorFlow status.

### 5. Check Active Jobs (if processing expected)

Call `get_runner_status` and `get_pipeline_stats` to see if jobs are running and pipeline state.

### 6. Read Debug Log (for detailed errors)

Call `read_debug_log` with optional `lines` to see recent error messages.

## Server Selection

- **stdio (DB/jobs, no WebUI)**: `imgscore-py-stdio` if workspace is **image-scoring**; `imgscore-el-stdio` if workspace is **electron-image-scoring**
- **WebUI / `execute_code`**: `imgscore-py-sse` or `imgscore-el-mcp-sse` (same endpoint; use the key from your open workspace)

## Terminology

Align with product UI: pipeline stages are **Discovery → Inspection → Quality Analysis → Similarity Clustering → Tagging**; DB uses `phase_code`; REST uses `scoring` / `tagging` / `clustering`. See **[docs/technical/PIPELINE_TERMINOLOGY.md](../../../docs/technical/PIPELINE_TERMINOLOGY.md)**.

## References

- [AGENTS.md](../../../AGENTS.md) — Common Workflows, Quick Decision Tree
- [.agent/mcp_tools_reference.md](../../../.agent/mcp_tools_reference.md) — Tool parameters
- [.cursor/rules/image-scoring-mcp.mdc](../../rules/image-scoring-mcp.mdc) — image-scoring vs mcp-firebird
