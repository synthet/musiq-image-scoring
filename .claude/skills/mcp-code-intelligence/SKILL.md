---
name: mcp-code-intelligence
description: >-
  Compare MCP code-intelligence layers — CLI wrappers, ast-grep, symbol/graph
  tools, Zoekt, embeddings. Use when choosing search/dispatch vs heavyweight
  indexes. Backend domain MCP is image-scoring-mcp (is-be-mcp).
---

# MCP code intelligence

Compare approaches for giving coding agents repository awareness.

## Purpose

Choose the lightest effective layer: CLI tools first, compact domain MCP second, graph/embedding indexes last.

## When to use

- Evaluating whether to add an MCP server vs using `rg`/`fd`
- Debugging agent search quality or memory use
- Complementing (not replacing) backend [`image-scoring-mcp`](../image-scoring-mcp/SKILL.md)

## Required tools

Depends on tier — baseline CLI from [agent-cli-hub](../agent-cli-hub/SKILL.md).

## Recommended tiers

### Minimal MCP setup

```text
rg + fd + read_file + git diff + patch_file
```

Lowest memory, transparent, deterministic. Best default for most tasks.

### Better setup

```text
fff MCP (ffgrep, fffind) + rg + fd + ast-grep + is-be-mcp search/dispatch + WSL pytest/doctor
```

Adds indexed file search for long agent sessions and compact pipeline triage via **`is-be-mcp`**. Keep `rg`/`fd` for one-off shell probes.

### Advanced setup

```text
Serena or codebase-memory-mcp + Zoekt + optional embeddings (e.g. claude-context)
```

Higher setup cost and memory. Use when repeated cross-repo symbol navigation justifies indexing.

**Warning:** Embedding-first indexing is often heavier and less exact than text/structural search — keep it secondary.

## Comparison matrix

| Layer | Examples | Strengths | Cost |
|-------|----------|-----------|------|
| Indexed file search | **fff** MCP (`ffgrep`, `fffind`) | Warm index, frecency, git-aware | User install |
| CLI wrappers | rg, fd, bat, git diff | Fast, bounded, no index | Agent orchestrates |
| Domain compact MCP | **`is-be-mcp`** search/dispatch | Pipeline, DB, diagnostics registry | Build `mcp-server/` |
| Structural | ast-grep, semgrep | Syntax shapes | Medium |
| Graph / embeddings | Serena, Zoekt, claude-context | Symbols, fuzzy discovery | Heavy |

## Backend domain MCP

For **Vexlum Scoring** pipeline, DB, and diagnostics — use compact **`search` + `dispatch`** on **`is-be-mcp`** (stdio) and optional **`is-be-live`** (SSE when WebUI runs).

See [`image-scoring-mcp`](../image-scoring-mcp/SKILL.md) and [AGENTS.md](../../../AGENTS.md).

Gallery triage: sibling workspace **`is-ui-mcp`**.

## Agent-safe patterns

- Start with Minimal tier; escalate only when text search fails repeatedly.
- Side-effecting `dispatch` requires `confirmed=True` per MCP contract.
- Bound MCP tool output; prefer dispatch actions with `limit` parameters.

## Commands requiring confirmation

- Installing/running new MCP servers that execute shell or network code
- Side-effecting dispatch without user approval
- Embedding index builds over entire monorepo without scope

See [commands-requiring-confirmation.md](../agent-cli-hub/references/commands-requiring-confirmation.md).

## Troubleshooting

- **MCP load failures:** `cd mcp-server && npm install && npm run build`
- **webui_unavailable:** WebUI not running — use stdio `is-be-mcp` local actions or start WebUI for SSE.

## Verification checklist

```bash
test -f mcp-server/dist/compactIndex.js && echo ok
rg --version && fd --version
```

Tools not verified in this pass: Serena, codebase-memory-mcp, Zoekt server, claude-context — treat as optional third-party.
