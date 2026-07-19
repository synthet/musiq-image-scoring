# /release — Semver release (Python backend)

Run a **semver release** for **this repo** (`image-scoring`) via the **compiled harness**.
Bump `APP_VERSION`, update `CHANGELOG.md`, then commit/push **only if the user asked**.

## Compiled bootloader (do this first)

```powershell
python scripts/agent_skills/release_bump.py inspect
python scripts/agent_skills/release_bump.py plan --level <major|minor|patch>   # if needed
python scripts/agent_skills/release_bump.py apply --level <major|minor|patch>
```

- Skill: `release-bump` (`.cursor/skills/release-bump/SKILL.md`)
- If `needs_llm_judgment` is true: classify changes from `git log` / diff, then pass `--level`.
- Do **not** hand-edit `modules/version.py` / `CHANGELOG.md` unless the harness fails.

## Before you start

- Do **not** commit scratch files (`tmp/`, root `test_*.py`, `__pycache__`, secrets).
- Changelog format: [Keep a Changelog](https://keepachangelog.com/).

## Semver rubric (majority rule; encoded in harness)

| Kind | Examples |
|------|----------|
| **Breaking** | API/DB contract breaks, removed endpoints, migrations needing operator action |
| **Feature** | New endpoints, pipeline phases, MCP tools, user-visible behavior |
| **Fix** | Bug fixes, robustness |
| **Chore** | Docs-only, comments, internal refactors |

1. Any breaking → **major**
2. Else feature ≥ fix and feature ≥ 1 → **minor**; fix > feature → **patch**
3. Changelog/docs-only → **patch**
4. User-stated `major` / `minor` / `patch` wins

## Commit and push (human gate)

Only when the user explicitly asks:

```bash
git add CHANGELOG.md modules/version.py
# plus other vetted files that belong in this release
git commit -m "chore: release v<newVersion>"
git push
```

On push failure, reconcile with remote, then push. Report the new version and a short summary.

## Related

- [`.agent/SKILL_COMPILATION.md`](../.agent/SKILL_COMPILATION.md)
