---
name: image-scoring-mcp
description: Vexlum Scoring MCP — compact search+dispatch on is-be-mcp / is-be-live and gallery is-ui-mcp / is-ui-live.
---

# Vexlum Scoring MCP server

**Canonical skill:** [`.cursor/skills/image-scoring-mcp/SKILL.md`](../../.cursor/skills/image-scoring-mcp/SKILL.md) — edit there first (AST10).

**Compact contract:** [docs/technical/MCP_SEARCH_DISPATCH.md](../../../docs/technical/MCP_SEARCH_DISPATCH.md). Action registry: [`mcp/action_registry.json`](../../../mcp/action_registry.json).

## Agent rules (is-be-mcp)

1. Tools are **`search`** and **`dispatch` only** on compact stdio — not raw `execute_sql`, `get_error_summary`, etc.
2. **`search` before `dispatch`** when unsure; use `include_schemas=True` for args.
3. Use **`action_id`** from search results (`category.tool`). Legacy bare names (e.g. `execute_sql`) resolve when registered.
4. On **`unknown_action`**, use `details.suggestions` — do not invent ids from AGENTS.md.
5. Maintenance / `execute_code` → **`is-be-live`** + `MCP_SSE_PROFILE=full`.

See canonical skill for the full compact action table and workflows.
