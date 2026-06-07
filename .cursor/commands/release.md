# Release (Python backend)

Run a **semver release** for **this repo** (`image-scoring`): bump `APP_VERSION`, update `CHANGELOG.md`, commit, and push.

## Before you start

- Do **not** commit scratch files (`tmp/`, `test_*.py` at root, `__pycache__`, secrets). Stage only intentional release files.
- Changelog format follows [Keep a Changelog](https://keepachangelog.com/) — see the top of `CHANGELOG.md`.

## 1. Inspect what will ship

- `git status --short` and `git diff --stat` (and `git diff` where needed).
- Current version: `modules/version.py` → `APP_VERSION = "X.Y.Z"`.
- Changelog: note `## [Unreleased]` contents (if any) and the latest numbered `## [X.Y.Z]`.

## 2. Choose the next semver (majority rule)

Classify changes into:

| Kind | Examples |
|------|----------|
| **Breaking** | API/DB contract breaks, removed endpoints, migrations that require operator action |
| **Feature** | New endpoints, pipeline phases, MCP tools, user-visible behavior |
| **Fix** | Bug fixes, robustness |
| **Chore** | Docs-only, comments, internal refactors |

**Bump rules (apply in order):**

1. If **any** breaking item → **major** (`X+1.0.0`).
2. Else compare **feature** vs **fix** counts (ignore pure **chore** when both exist). If **feature ≥ fix** and **feature ≥ 1** → **minor** (`x.Y+1.0`). If **fix > feature** → **patch** (`x.y.Z+1`).
3. Changelog/docs-only → **patch**.

If the user stated `major` / `minor` / `patch`, use that.

## 3. Edit files

- **`CHANGELOG.md`**:
  - Add `## [newVersion] - YYYY-MM-DD` below the header / intro (and above older releases).
  - Move any bullets out of `## [Unreleased]` into this section (or fold Unreleased into the new section), then leave `## [Unreleased]` empty or with a placeholder for future work — match project style.
- **`modules/version.py`**: Set `APP_VERSION = "newVersion"` (must match changelog).

## 4. Commit and push

```bash
git add CHANGELOG.md modules/version.py
# plus other vetted files that belong in this release
git commit -m "chore: release v<newVersion>"
git push
```

On push failure, reconcile with remote, then push. Report the new version and a short summary.
