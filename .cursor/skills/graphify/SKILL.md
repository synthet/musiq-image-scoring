---
name: graphify
description: >-
  Use Graphify knowledge-graph MCP (graphify-be) or CLI for architecture /
  cross-module connectivity. Prefer after rg/fff fail for “how does X connect
  to Y”; never for pipeline/DB triage (use is-be-mcp).
---

# Graphify (architecture graph)

Local AST knowledge graph — no vector store. Soft rule: [`.cursor/rules/graphify.mdc`](../../rules/graphify.mdc) (`alwaysApply: false`).

## When to use

- Cross-module “how does X connect to Y”, god nodes, community / subsystem maps
- `graphify-out/graph.json` exists (build: `graphify . --code-only`)
- MCP server **`graphify-be`** is connected (or fall back to CLI)

## When not to use

| Need | Use instead |
|------|-------------|
| Scoring / DB / job failures | [`image-scoring-mcp`](../image-scoring-mcp/SKILL.md) (`is-be-mcp`) |
| Literal string / filename | [`agent-search`](../agent-search/SKILL.md) / **fff-be** |
| Graph missing | `graphify . --code-only` then retry; do not invent edges |

## Setup

1. `uv tool install "graphifyy[mcp]"` (CLI + `graphify-mcp`)
2. First build: `graphify . --code-only` → `graphify-out/` (gitignored)
3. Enable in [`.cursor/mcp.json`](../../mcp.json) (from [mcp.example.json](../../mcp.example.json)):

```json
"graphify-be": {
  "command": "graphify-mcp",
  "args": ["graphify-out/graph.json"],
  "cwd": "${workspaceFolder:image-scoring-backend}"
}
```

4. Reload Cursor MCP. Before calling tools: check schema via MCP descriptors.

## MCP tools (`graphify-be`)

| Tool | Args | Use for |
|------|------|---------|
| `graph_stats` | (none) | Sanity check — node/edge/community counts |
| `query_graph` | `question` (req); `mode` bfs\|dfs; `depth` 1–6; `token_budget` | Natural-language / keyword subgraph |
| `get_node` | `label` | One symbol / file node |
| `get_neighbors` | `label`; optional `relation_filter` | Direct edges |
| `get_community` | `community_id` | Subsystem cluster |
| `god_nodes` | optional `top_n` | Highest-degree hubs |
| `shortest_path` | `source`, `target`; optional `max_hops` | Path between two concepts |
| `list_prs` / `get_pr_impact` / `triage_prs` | GitHub PR impact (needs `gh` / network) | PR blast radius — skip unless user asks |

All tools accept optional `project_path` (absolute dir with `graphify-out/graph.json`).

## Preferred workflow

```text
graph_stats()                                    # confirm graph loaded
query_graph({question: "how does ScoringRunner relate to PhaseCode"})
get_node({label: "ScoringRunner"})               # if you have a name
shortest_path({source: "ScoringRunner", target: "create_api_router"})
```

If MCP is unavailable, CLI equivalents:

```bash
graphify query "how does ScoringRunner relate to PhaseCode"
graphify explain "ScoringRunner"
graphify path "ScoringRunner" "create_api_router"
```

## Agent-safe patterns

- Start with `depth` 2–3 and default `token_budget`; raise budget or narrow `question` if truncated.
- Prefer `context_filter: ["call"]` (or similar) when the question is about call edges only.
- Do not paste secrets; do not re-index `secrets.json` / thumbnails (see `.graphifyignore`).
- Do **not** run stock `graphify cursor install` (alwaysApply / hooks) — soft rule only.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| MCP server missing in Cursor | Reload MCP; confirm `.cursor/mcp.json` has `graphify-be` and `graphify-out/graph.json` exists |
| `no LLM API key` on build | Use `graphify . --code-only` |
| Stale graph after big refactors | Re-run `graphify . --code-only` then `graphify cluster-only .` |
| `ModuleNotFoundError: graphify` with plain `python` | Use `graphify-mcp` / uv-tool Python, not `~/.venvs/tf` |

## Related

- Install tier: [agent-cli-hub install-tiers](../agent-cli-hub/references/install-tiers.md) (Deferred)
- Layer choice: [mcp-code-intelligence](../mcp-code-intelligence/SKILL.md)
- AGENTS.md § Graphify
