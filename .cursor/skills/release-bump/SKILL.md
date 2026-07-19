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

## Canonical flow

```powershell
# 1. Inspect (deterministic)
python scripts/agent_skills/release_bump.py inspect

# 2. If needs_llm_judgment: classify git history, then pass --level
python scripts/agent_skills/release_bump.py plan --level minor   # or major|patch

# 3. Apply file writes only (no git)
python scripts/agent_skills/release_bump.py apply --level minor
```

## Ownership split

| Owner | Responsibility |
|-------|----------------|
| **Code** | Read `modules/version.py`, parse `CHANGELOG.md`, bump math, rewrite files |
| **LLM** | Only when `needs_llm_judgment` is true (empty/ambiguous Unreleased) |
| **Human** | Commit, tag, push — only when explicitly requested |

## Semver rubric (encoded in harness; override with `--level`)

1. Breaking / removed → **major**
2. Else if Added count ≥ Fixed and Added ≥ 1 → **minor**
3. Else Fixed-dominant or Changed-only → **patch**

## After apply

- Suggest `chore: release vX.Y.Z` (do not commit unless asked).
- Optional verify: fast pytest / ruff from **AGENTS.md**.
- Slash command `/release` follows the same harness, then may commit/push **only if the user asked**.

## Related

- Compilation notes: [`.agent/SKILL_COMPILATION.md`](../../.agent/SKILL_COMPILATION.md)
- Command: [`.cursor/commands/release.md`](../../.cursor/commands/release.md)
