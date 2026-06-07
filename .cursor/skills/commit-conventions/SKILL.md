---
name: commit-conventions
description: Apply Conventional Commits and consistent PR titles when the user asks for commit messages, PR titles, or changelog-ready wording.
---

# Commit conventions

## When to use

- User asks for a **commit message**, **PR title**, or **branch name**.
- User runs `/pr-ready` and wants aligned messaging.

## Conventional Commits (summary)

Format: `type(scope optional): description`

Common **types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`, `perf`, `build`.

Rules:

- Description is **imperative**, lowercase, no trailing period: `fix auth redirect`, not `Fixed.`
- **Breaking change**: footer `BREAKING CHANGE: ...` or `feat!:` / `fix!:`.
- **Scope** is optional; use the area touched (`api`, `cli`, `deps`).

## PR titles

- Same as commit subject line for single-commit PRs.
- For multi-commit PRs, summarize the **user outcome**: `feat(search): add fuzzy matching`.

## Body (optional)

- What changed and why (not how every line moved).
- Link issues: `Fixes #123`.

## Project overrides

If **AGENTS.md** or `CONTRIBUTING.md` defines different rules, follow those first.
