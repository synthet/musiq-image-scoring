---
name: release-bump
description: Bump the project version with a semver rubric, promote the Unreleased changelog section, and verify before committing. Use when the user asks to cut a release, bump the version, or tag a new version.
---

# Release bump

Repeatable release procedure: decide the semver level, update the version and `CHANGELOG.md`,
verify, and prepare (not push) the release commit.

## 1. Detect the version source

Find where the version lives, in this order: `modules/version.py`, `pyproject.toml` / `setup.cfg`,
`package.json` (frontend), a `VERSION` file, or a documented constant. If none exists, ask the user
where the version should live instead of inventing one.

## 2. Choose the bump (semver rubric)

Review changes since the last release (`git log <last-tag>..HEAD` and the `Unreleased` section of
`CHANGELOG.md`):

- **major** — any breaking change: removed/renamed public API, config key, schema field, or CLI
  flag; behavior change that requires consumer action.
- **minor** — new backward-compatible capability (new command, skill, endpoint, option).
- **patch** — bug fixes, docs, internal refactors with no contract change.

State the chosen level and the one or two changes that justify it.

## 3. Update files

1. Bump the version in the detected source.
2. In `CHANGELOG.md` (Keep a Changelog): rename `## [Unreleased]` to `## [X.Y.Z] — YYYY-MM-DD`,
   keeping its subsections, and add a fresh empty `## [Unreleased]` above it. Drop empty
   subsections; keep entries as complete sentences.

## 4. Verify

Run the project's checks from **AGENTS.md** (ruff, fast pytest subset). Do not proceed with failing checks.

## 5. Commit and tag — only when the user asks

Suggest a Conventional Commit (`chore(release): vX.Y.Z`) and the matching annotated tag
(`git tag -a vX.Y.Z`). Do not commit, tag, or push without an explicit request.
