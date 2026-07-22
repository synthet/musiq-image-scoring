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

---

## 2026-07-04 alignment (Cursor-first, hub layout)

Source: [synthet-code-framework README](https://github.com/synthet/synthet-code-framework/blob/main/README.md). **Approved forks** (do not revert blindly):

| Topic | Framework default | Image-scoring repos |
|-------|-----------------|---------------------|
| Canonical tree | `.claude/` → `.cursor/` | **`.cursor/` → `.claude/`** |
| CLI skills | 13 flat skills under `cli-tools-overview` | **7 consolidated** (`agent-cli-hub` + 6 topics) |
| fff MCP | Template mentions user-level | **Project-level** `fff-be` / `fff-gallery` only |

### Framework 13 skills → 7 hub skills (content map)

| Framework skill | Hub equivalent |
|-----------------|----------------|
| `cli-tools-overview` | `agent-cli-hub` + `references/*` |
| `search-tool-selection` | `agent-search/references/tool-selection.md` |
| `safe-command-patterns` | `agent-cli-hub/references/bounded-output-patterns.md`, `commands-requiring-confirmation.md` |
| `search-and-navigation` | `agent-search` |
| `structural-code-search` | `agent-search` (ast-grep section) |
| `git-and-diff-workflows` | `agent-git-workflows` |
| `data-config-tools` | `agent-data-config` |
| `task-env-package-tools` | `agent-dev-tooling` |
| `lint-format-security` | `agent-dev-tooling` |
| `mcp-code-intelligence` | `mcp-code-intelligence` |
| `install-checklist` | `agent-cli-hub/references/install-tiers.md`, `install-blocks.md` |
| `windows-agent-tooling` | `agent-platform-tooling` (Windows) |
| `wsl2-agent-tooling` | `agent-platform-tooling` (WSL) |

Shared references (6 files under hub `references/`) match framework `cli-tools-overview/references/`.

### Status after 2026-07-04 work

| Asset | Backend | Gallery |
|-------|---------|---------|
| SDLC commands + validate-implementation | Done | Done |
| 7 CLI hub skills + validate script | Done | Done |
| `sync_assistant_trees.py` + `agent-infra.yml` | Done | **Ported** |
| `check_agent_frontmatter.py`, `check_secrets.py` | Done | **Ported** |
| Memory (`agent-memory`, `/log-session` …) | Done | **Ported** (scripts via sibling backend) |
| `safety-and-secrets` rule | **Added** | **Added** |
| `docs/ai-workflow` Framework alignment section | **Added** | **Added** |

### Verify (both app repos)

```bash
python scripts/sync_assistant_trees.py --check
python scripts/validate_cli_hub_skills.py
python scripts/ci/check_agent_frontmatter.py
python scripts/ci/check_secrets.py
```

---

## 2026-07-21 onboard (post-0.1.0 framework gaps)

Source: [synthet-code-framework](https://github.com/synthet/synthet-code-framework) HEAD after Spec Kit + disciplined-skills work (~2026-07-19). Issues: backend [#301](https://github.com/synthet/image-scoring-backend/issues/301), gallery [#159](https://github.com/synthet/image-scoring-gallery/issues/159).

| Asset | Backend | Gallery | Notes |
|-------|---------|---------|-------|
| `/clarify`, `/tasks`, `/analyze` + workflows | Added | Added | Spec Kit quality gates |
| `.agent/SPEC_KIT_ADOPTION.md` | Added | Added | Cursor-first sync wording |
| `/spec` product scenario + assumptions | Updated | Updated | Light cherry-pick |
| `karpathy-coding` rule + `karpathy-guidelines` skill | Added | Added | Always-on coding behavior |
| `systematic-debugging`, `test-driven-development`, `skill-authoring` | Added | Added | Prose skills |
| `verification-before-completion` | Skill + `scripts/agent_skills/verification_before_completion.py` | Skill (npm/tsc proofs) | Backend harness layout preserved |
| `commit-and-push` | Skill + `scripts/agent_skills/commit_and_push.py` | Skipped | Gallery keeps `changelog-commit-push` |
| Flat 13 CLI skills | Not ported | Not ported | Hub remains |

Approved forks unchanged: Cursor-first, 7-skill CLI hub, project-level fff, `scripts/agent_skills/` harnesses.
