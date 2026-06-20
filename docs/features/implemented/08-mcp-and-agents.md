---
type: Implemented Feature
title: MCP and agents
description: Compact Node stdio MCP (search, dispatch, sse_status) for IDE agents; optional is-be-live SSE for legacy tools and execute_code.
resource: docs/features/implemented/08-mcp-and-agents.md
tags: [mcp, agents, implemented]
timestamp: 2026-06-20T00:00:00Z
okf_version: 0.1
---

# MCP and agents

**Purpose:** Expose a **stable tool surface** for IDE agents and operators: DB diagnostics, job inspection, similarity helpers, guarded SQL, and optional in-process `execute_code` when SSE + env flags allow.

**User-visible behavior:** Cursor attaches **`is-be-mcp`** via `node mcp-server/dist/compactIndex.js` (stdio). Tools: **`search`**, **`dispatch`**, **`sse_status`**. Optional **`is-be-live`** SSE when WebUI is running.

**Primary code paths:**

| Layer | Path |
|-------|------|
| Node stdio MCP | `mcp-server/src/compactIndex.ts`, `createBackendCompactMcpServer.ts` |
| Python handlers | `modules/mcp/compact_tools.py`, `scripts/mcp/compact_worker.py` |
| Legacy full tool surface | `modules/mcp_server.py` (FastMCP; SSE with `MCP_SSE_PROFILE=full`) |

**Setup:** [guides/setup/mcp-compact-servers.md](../../guides/setup/mcp-compact-servers.md) · Contract: [MCP_SEARCH_DISPATCH.md](../../technical/MCP_SEARCH_DISPATCH.md) · [AGENTS.md](../../../AGENTS.md)

**Related docs:** [AGENT_COORDINATION](../../technical/AGENT_COORDINATION.md) · [MCP_DEBUGGING_TOOLS](../../technical/MCP_DEBUGGING_TOOLS.md) · [.agent/mcp_tools_reference.md](../../../.agent/mcp_tools_reference.md)
