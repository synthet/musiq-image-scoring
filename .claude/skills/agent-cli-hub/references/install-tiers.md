# Install tiers

Tiered install order for **image-scoring-backend** agent CLI skills. Block A commands live in [install-blocks.md](install-blocks.md) — do not duplicate full winget blocks here.

## Tier overview

| Tier | What | When to install |
|------|------|-----------------|
| **Tier 0 (router core)** | `git`, `rg`, `fd`, `jq`, Python (WSL + venv) | First — hub and most skills assume these |
| **Block A (canonical)** | Full block in [install-blocks.md](install-blocks.md) | Core agent workflow on your platform |
| **Block B (extensions)** | Child-skill tools not in Block A | Recommended full agent workflow |
| **Deferred** | Optional per skill | Only when that skill's task needs them |

## Install scopes (operator choice)

| Scope | Includes |
|-------|----------|
| **Core only** | Tier 0 + any missing Block A tools from install-blocks |
| **Recommended** | Block A + Block B |
| **Everything missing** | Recommended + deferred tools you expect to use |

After any winget/uv/npm install, see [agent-environment.md](agent-environment.md) — restart Cursor and smoke-test PATH.

## Tier 0 — router core

Must respond before other skills:

```powershell
git --version; rg --version; fd --version; jq --version
```

WSL (primary for Python/scripts):

```bash
source ~/.venvs/tf/bin/activate
python --version
python scripts/doctor.py --no-gpu
```

Install missing tools via Block A in [install-blocks.md](install-blocks.md).

## Block A — canonical (install-blocks.md)

Tools in the Windows winget / WSL apt / Homebrew blocks:

- `git`, `gh`, `rg`, `fd`, `jq`, `delta`, `bat`, `zoxide`
- `ast-grep` (`sg` via npm global)
- `uv`, `ruff`, `pyright` — **primary** for this repo (WSL venvs)
- Optional: `node` (+ npm) for `mcp-server/` build

**Note:** Prefer standalone winget `rg` on Windows even if Cursor bundles its own ripgrep for IDE search.

## Block B — child-skill extensions

Not listed in Block A install-blocks; install when pursuing **Recommended** scope.

| Tool | Child skill | Windows (winget) |
|------|-------------|------------------|
| `yq` | [agent-data-config](../../agent-data-config/SKILL.md) | `MikeFarah.yq` |
| `just` | [agent-dev-tooling](../../agent-dev-tooling/SKILL.md) | `casey.just` |
| `mise` | agent-dev-tooling | `jdx.mise` |
| `direnv` | agent-dev-tooling | `direnv.direnv` |
| `eza` | [agent-search](../../agent-search/SKILL.md) | `eza-community.eza` |
| `shellcheck` | agent-dev-tooling | `koalaman.shellcheck` |
| `trivy` | agent-dev-tooling | `AquaSecurity.Trivy` |
| `hadolint` | agent-dev-tooling | `hadolint.hadolint` |

### Block B — one-shot Windows example

```powershell
winget install MikeFarah.yq casey.just jdx.mise direnv.direnv eza-community.eza koalaman.shellcheck AquaSecurity.Trivy hadolint.hadolint
```

Confirm IDs with `winget search` on locked-down machines.

## Deferred — optional

| Tool | Skill | When |
|------|-------|------|
| `fzf` | agent-search | Human interactive pick |
| `semgrep` | agent-search | Rule/security scans (`--dryrun` default) |
| `hyperfine` | agent-dev-tooling | Benchmarking |
| `gitleaks` | [agent-git-workflows](../../agent-git-workflows/SKILL.md) | Secret scan before sharing diffs |
| `ctags` / `tree-sitter` | agent-search | Repeated def/ref sessions |
| `fff-mcp` | agent-search, mcp-code-intelligence | Project **`fff-be`** in `.cursor/mcp.json` — [AGENTS.md § fff](../../../../AGENTS.md) |
| `graphifyy` (CLI: `graphify`) | agent-search, mcp-code-intelligence | Architecture / cross-module graph — `uv tool install graphifyy`; first build `graphify . --code-only` (no API key); optional MCP `graphifyy[mcp]` — [AGENTS.md § Graphify](../../../../AGENTS.md) |

## Backend verification (after install)

WSL + `~/.venvs/tf`:

```bash
fd --version; bat --version; sg --version; ruff --version
python scripts/doctor.py --no-gpu
ruff check modules/ --statistics
python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py -q --tb=no
```

Full environment checklist: [agent-environment.md](agent-environment.md).

## Human provisioning (install-checklist)

**Agents:** recommend install tiers to the user; do **not** run bulk `winget install` without approval.

1. Pick scope: Core only / Recommended / Everything missing (table above).
2. User runs blocks from [install-blocks.md](install-blocks.md) interactively.
3. **Restart Cursor** after installs; smoke-test per [agent-environment.md](agent-environment.md).

Verification after install:

- [ ] `git --version`, `rg --version`, `fd --version`, `jq --version`, `gh --version`
- [ ] WSL: `source ~/.venvs/tf/bin/activate && python --version`
- [ ] Block B (Recommended): `yq --version`, `just --version`, `shellcheck --version`
- [ ] `python scripts/doctor.py --no-gpu` (backend health)
