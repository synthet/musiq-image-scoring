---
description: Conventions for maintaining docs/ as an OKF-aligned wiki — metadata, categories, indexes, log, cross-references
globs: "docs/**"
alwaysApply: false
---

# Documentation wiki (image-scoring-backend)

Applies when creating, materially editing, renaming, or reorganizing files under `docs/`.

## Read first

- Start agents from `docs/OKF_ADOPTION.md`, `docs/CANONICAL_SOURCES.md`, and `docs/WIKI_SCHEMA.md`.
- Use `docs/OKF_ADOPTION.md` as the local Open Knowledge Format (OKF) profile for frontmatter, type vocabulary, folder/index behavior, and migration policy.

## OKF metadata

- Treat `docs/` as an OKF-aligned knowledge bundle: markdown concept pages with YAML frontmatter, relative markdown links, folder indexes, and append-only `docs/log.md` entries.
- New living docs and materially edited living docs should begin with YAML frontmatter containing at least `type`; prefer `title`, `description`, `resource`, `tags`, `timestamp`, and `okf_version: 0.1` as described in `docs/OKF_ADOPTION.md`.
- Choose clear human-readable `type` values from the OKF profile when possible, such as `Documentation Hub`, `Documentation Index`, `Technical Reference`, `Runbook`, `Guide`, `Feature Spec`, `Implemented Feature`, `Report`, or `Archive`.
- Do not bulk-edit archived snapshots or perform rename-only churn solely to add OKF metadata; add metadata opportunistically when content changes.

## Categories

| Folder | Use for |
|--------|---------|
| `docs/architecture/` | System overview, pipeline diagrams, DB connector proposals |
| `docs/guides/` | How-tos (`getting-started/`, `setup/`) |
| `docs/features/planned/` | Specs for not-yet-shipped product work (including `embeddings/`) |
| `docs/planning/` | Migrations, schema phases, refactors, model roadmaps |
| `docs/technical/` | Stable reference; keep `UPPER_CASE.md` names unless a deliberate rename |
| `docs/reports/` | Point-in-time audits; move stale snapshots to `docs/archive/reports/` |
| `docs/archive/` | Deprecated or superseded material |

## Rules

- Use **relative** markdown links; cross-repo links to **image-scoring-gallery** use full GitHub URLs when needed.
- Prefer small linked concept pages over duplicated mega-docs; indexes should route readers rather than restate canonical content.
- After additions or moves: update the nearest folder `INDEX.md`, root `docs/INDEX.md`, and `docs/README.md` when the hub changes.
- Append one line to `docs/log.md` for significant wiki operations (see `WIKI_SCHEMA.md`).
