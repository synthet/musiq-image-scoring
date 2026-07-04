---
name: mcp-server-design
description: Design and implement an MCP server's tools, resources, and prompts with safe transport and input validation. Use when building or extending a Model Context Protocol server for agent integration.
---

# MCP server design

## Use this skill when

- Creating or extending an MCP server that exposes this project to AI agents (`modules/mcp_server.py`, `mcp-server/`)
- Adding tools, resources, or prompts
- Configuring `.cursor/mcp.example.json`

## Procedure

1. Read the [MCP specification](https://modelcontextprotocol.io/specification) and `docs/technical/MCP_SEARCH_DISPATCH.md`.
2. Pick a clear, stable **server name** and a tool-naming scheme (`category.tool` for compact dispatch).
3. **Transport:** stdio by default (`is-be-mcp`); optional SSE (`is-be-live` / WebUI). Pass secrets via **environment variables**, never CLI args.
4. **Tools** — validate every input with a schema (pydantic). Prefer compact **`search` + `dispatch`** over dozens of raw tools when the domain is large.
5. **Separate read from write.** Read-only tools are safe-by-default; **write/side-effecting tools**
   must require explicit confirmation (`confirmed=True` and `ALLOWED_SIDE_EFFECT_ACTIONS` allowlist).
6. **Resources** — expose read-only context (status, schema, recent events) — **no secrets**.
7. **Prompts** — ship reusable prompt templates for common workflows where helpful.
8. On a downstream/dependency failure: return **structured diagnostics**, do not throw opaque errors.
9. Test tool handlers with mocked dependencies (no live side effects in unit tests).
10. Regenerate inventory: `python scripts/generate_mcp_tool_inventory.py --update-docs AGENTS.md`.

## Safety checks

- No raw shell / file / network / arbitrary-code tools without an explicit approval policy.
- All tool inputs validated against a schema.
- Side-effecting tools gated behind confirmation + allowlist; `execute_code` requires `ENABLE_MCP_EXECUTE_CODE=1`.
  See [.agent/SAFETY.md](../../../.agent/SAFETY.md).

## Done criteria

- Tool list matches the published schemas; descriptions are accurate and current.
- Secrets only via env; never logged or returned in tool output.
- Build produces the server entrypoint referenced by your MCP config.
- AGENTS.md inventory regenerated when the tool set changes.

References: [MCP docs](https://modelcontextprotocol.io), `docs/guides/setup/mcp-compact-servers.md`.
