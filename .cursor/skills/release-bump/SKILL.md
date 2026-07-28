---
name: release-bump
description: >-
  Bump semver + promote CHANGELOG Unreleased via compiled harness. Use for /release,
  version bumps, or tagging. Runs scripts/agent_skills/release_bump.py; LLM only
  when Unreleased is ambiguous. Never commit/push unless the user asks.
---

# Release bump (compiled)

Thin bootloader over `scripts/agent_skills/release_bump.py`. Do **not** re-discover
version/changelog paths or semver math — run the harness.

## Invoke

```powershell
# 1. Inspect (deterministic)
python scripts/agent_skills/release_bump.py inspect

# 2. If needs_llm_judgment: fill Unreleased + choose level (see slots below), then:
python scripts/agent_skills/release_bump.py plan --level minor   # or major|patch

# 3. Apply file writes only (no git)
python scripts/agent_skills/release_bump.py apply --level minor
```

## LLM judgment slots

1. **Level** — when `needs_llm_judgment` is true, classify `major|minor|patch` from `git log` / diff since the last version (see semver rubric below).
2. **Unreleased bullets** — when Unreleased is empty or ambiguous, write Keep-a-Changelog bullets under `## [Unreleased]` for **committed** work since the last version, **then** `plan` / `apply`. Hand-editing Unreleased in that case is expected (harness otherwise promotes “Release housekeeping”). Do **not** hand-edit `modules/version.py`.
3. **Dirty tree** — if `inspect.git_status` shows related WIP: either add those bullets and stage the files with the release commit, or omit them from notes and tell the user. Never document uncommitted work as shipped.

## Human authority

- Commit, tag, push — only when the user explicitly asks.
- Suggest `chore: release vX.Y.Z` after apply; do not ship without a request.

## Ownership split

| Owner | Responsibility |
|-------|----------------|
| **Code** | Read `modules/version.py`, parse `CHANGELOG.md`, bump math, rewrite files on `apply` |
| **LLM** | Level + Unreleased draft when `needs_llm_judgment`; dirty-tree include/exclude call |
| **Human** | Commit, tag, push |

## Semver rubric (encoded in harness; override with `--level`)

1. Breaking / removed → **major**
2. Else if Added count ≥ Fixed and Added ≥ 1 → **minor**
3. Else Fixed-dominant or Changed-only → **patch**

## Verify

- Optional: fast pytest / ruff from **AGENTS.md** after apply.
- Slash command `/release` follows the same harness.

## Related

- Compilation notes: [`.agent/SKILL_COMPILATION.md`](../../.agent/SKILL_COMPILATION.md)
- Command: [`.cursor/commands/release.md`](../../.cursor/commands/release.md)
