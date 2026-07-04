# synthet-code-framework port manifest

Generated during framework adoption (2026-07-01). Source: `../synthet-code-framework` (generic upstream).

## Commands

| Asset | Backend before | Gallery before | Action |
|-------|----------------|----------------|--------|
| `spec.md` (EARS AC-n) | Given/When/Then | Same | **Port** |
| `plan.md` | Missing (listed in AGENTS) | Present | **Add backend** |
| `pr-ready.md` (validate-implementation gate) | Partial | Partial | **Port** |
| `decompose.md` | Missing | Present | **Add backend** |
| Other SDLC commands | Present | Present | Keep |

## Skills

| Skill | Backend | Gallery | Action |
|-------|---------|---------|--------|
| `validate-implementation` | Missing | Missing | **Port both** |
| `release-bump` | Missing | Missing | **Port backend** |
| `threat-modeling-agentic-tools` | Missing | Missing | **Port both** |
| `mcp-server-design` | Missing | Missing | **Port both** |
| `eval` | Missing | Present | **Port backend** |
| Domain skills (imgscore-*, gallery-*, wsl-*, …) | Present | Present | **Keep** |

## CI / scripts

| Script | Backend | Action |
|--------|---------|--------|
| `check_agent_frontmatter.py` | Missing | **Port** (adapt for `.cursor/` canonical) |
| `check_secrets.py` | Missing | **Port** |
| `sync_assistant_trees.py` | Missing | **Port** (`--direction cursor-to-claude`, default) |

## Docs

| Doc | Action |
|-----|--------|
| `docs/ai-workflow/README.md` | **Add** (Cursor-first variant) |
| Upstream note in `AGENTS.md` | **Add** |

## Do not port

- `bootstrap.py`, framework self-tests
- Generic rules replacing 16 domain rules
- Empty MCP templates

## Sync policy

- **Canonical:** `.cursor/` (backend, gallery)
- **Mirror:** `.claude/` via `scripts/sync_assistant_trees.py --direction cursor-to-claude`
- **Drift CI:** `sync_assistant_trees.py --check`
