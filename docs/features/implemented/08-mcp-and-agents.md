# MCP and agents

**Purpose:** Expose a **stable tool surface** for IDE agents and operators: DB diagnostics, job inspection, similarity helpers, guarded SQL, and optional in-process `execute_code` when SSE + env flags allow.

**User-visible behavior:** Cursor / Claude attach the MCP server (stdio from repo root or SSE from running WebUI); tools mirror maintenance workflows documented in AGENTS.

**Primary code paths:** `modules/mcp_server.py` (FastMCP tool registration), optional HTTP bridge in `modules/mcp_http_client.py`.

**Main integration:** No first-class REST “MCP” path in the feature sense; transport is **stdio** (`python -m modules.mcp_server`) or **SSE** (`/mcp/sse` when WebUI enables MCP). See repo root [AGENTS.md](../../../AGENTS.md) for counts, config keys, and troubleshooting.

**Related docs:** [AGENT_COORDINATION](../../technical/AGENT_COORDINATION.md) · [MCP_DEBUGGING_TOOLS](../../technical/MCP_DEBUGGING_TOOLS.md) · [.agent/mcp_tools_reference.md](../../../.agent/mcp_tools_reference.md)
