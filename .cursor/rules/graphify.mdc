---
description: Soft Graphify guidance — architecture / cross-module connectivity via knowledge graph (not always-on)
alwaysApply: false
---

# Graphify (soft — architecture map)

Optional local knowledge graph for **code/architecture** questions. Prefer `rg` / **fff** / **`is-be-mcp`** first; escalate here for “how does X connect to Y”, god nodes, or subsystem maps.

## When to use

- `graphify-out/graph.json` exists (built via `graphify . --code-only` for AST-only, or full `graphify .` with an API key for docs/images)
- Cross-module connectivity, surprising links, or architecture overview
- Commands: `graphify query "…"`, `graphify path A B`, `graphify explain "…"`, or read `graphify-out/GRAPH_REPORT.md`

## When not to use

- Pipeline / DB / scoring triage → **`is-be-mcp`** `search` + `dispatch`
- Literal string or filename discovery → `rg` / `fd` / **fff-be**
- Graph not built yet → fall back to search; do not invent graph answers

## Safety

- Never index or paste `secrets.json`, `.env`, or credentials.
- Respect `.gitignore` + [`.graphifyignore`](../../.graphifyignore) (thumbnails, models, FirebirdLinux, scratch).
- Do **not** run stock `graphify cursor install` / `graphify claude install` in this repo — those set `alwaysApply: true` / hooks. Soft rule only.

## Install (operator)

```bash
uv tool install graphifyy          # CLI; package name has two y's
uv tool install "graphifyy[mcp]"   # optional MCP serve
graphify . --code-only             # first build → graphify-out/ (local AST, no API key)
# graphify .                       # full build (docs/images need GEMINI_API_KEY / OPENAI_API_KEY / etc.)
```

Optional MCP key **`graphify-be`**: see [AGENTS.md § Graphify](../../AGENTS.md) and [`.cursor/mcp.example.json`](../mcp.example.json). Use `uv`-tool Python on PATH (not `~/.venvs/tf`) for `python -m graphify.serve`.
