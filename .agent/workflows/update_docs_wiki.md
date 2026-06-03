---
description: Update backend docs / wiki safely
---

## Purpose

Add or reorganize `docs/` without breaking the wiki graph or canonical authority.

## When to use

- New feature docs, hub updates, cross-links after code changes.

## Canonical docs first

- [docs/WIKI_SCHEMA.md](../../docs/WIKI_SCHEMA.md)
- [docs/CANONICAL_SOURCES.md](../../docs/CANONICAL_SOURCES.md)
- [.cursor/rules/documentation.mdc](../../.cursor/rules/documentation.mdc)
- [.agent/skills/docs-wiki/SKILL.md](../skills/docs-wiki/SKILL.md)

## Safe process

1. Confirm whether the fact belongs in **technical** reference vs **planning** vs **report**.
2. Use **relative** links inside this repo; use **full GitHub URLs** to **image-scoring-gallery** when pointing at sibling docs.
3. Update hub lists: [docs/INDEX.md](../../docs/INDEX.md), [docs/README.md](../../docs/README.md) when a new hub entry is warranted.
4. Append one line to [docs/log.md](../../docs/log.md) for non-trivial edits.

## Do not

- Do not duplicate backend schema authority inside narrative docs — link `DB_SCHEMA.md` / `API_CONTRACT.md`.
- Do not delete historical reports without archive path and log entry.
