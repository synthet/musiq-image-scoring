# CLI tool skills — maintenance contract (hub layout)

Gallery uses a **consolidated hub** under `.cursor/skills/` (Cursor-first). Upstream flat-13 variant lives in [synthet-code-framework](https://github.com/synthet/synthet-code-framework) (`.claude/skills/<name>/`).

## Goal

Maintain practical agent skills for lightweight CLI tools on Windows, WSL2, and macOS: fast search, safe edits, bounded output, reliable verification.

## Required deliverables (7 skills + references)

| Skill | Role |
|-------|------|
| `agent-cli-hub` | Router + shared `references/` |
| `agent-search` | Text + structural search; [references/tool-selection.md](../.cursor/skills/agent-search/references/tool-selection.md) |
| `agent-git-workflows` | git, gh, bounded diffs |
| `agent-data-config` | jq, yq, curl |
| `agent-dev-tooling` | Gallery npm lint/tsc/vitest first |
| `agent-platform-tooling` | Windows vs WSL2 |
| `mcp-code-intelligence` | MCP tiers; fff, embeddings warning |

Shared references under `agent-cli-hub/references/`:

- `install-blocks.md`
- `bounded-output-patterns.md`
- `commands-requiring-confirmation.md`
- `windows-wsl-split.md`

## Skill file requirements

Each topic `SKILL.md` includes at minimum:

- Purpose
- When to use
- Required tools
- Common commands
- Agent-safe patterns
- Commands requiring confirmation (or link to hub reference)
- Troubleshooting
- Verification checklist

Hub `SKILL.md` includes router table and links to references.

YAML frontmatter: `name` (first key, matches directory) + non-empty `description`.

## MCP tiers

```text
Minimal:  rg + fd + read_file + git diff + patch_file
Better:   fff MCP + rg + fd + ast-grep + git tools + npm run / task runner
Advanced: Serena or codebase-memory-mcp + Zoekt + optional embeddings
```

Embedding-first indexing is heavier — secondary to text/structural search.

## Validation

```bash
python scripts/validate_cli_hub_skills.py
python scripts/ci/check_agent_frontmatter.py   # when wired in CI
```

## Quality bar

Usable by another coding agent without extra explanation. Practical commands, safe workflows, clear platform distinctions.
