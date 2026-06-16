---
type: Documentation Governance
title: Open Knowledge Format Adoption
description: Local adoption plan for making docs/ an OKF-aligned, agent-readable knowledge bundle without disruptive renames.
resource: OKF_ADOPTION.md
tags: [docs, okf, agents, governance]
timestamp: 2026-06-16T00:00:00Z
okf_version: 0.1
---

# Open Knowledge Format adoption

This repository treats `docs/` as an **OKF-aligned knowledge bundle**: a directory of markdown concept files with small YAML frontmatter blocks, normal markdown cross-links, folder indexes, and an append-only activity log.

OKF alignment is intentionally incremental. The existing documentation tree remains stable for humans, GitHub links, Cursor/Claude rules, and sibling-repo references; new and materially edited living docs should add OKF-compatible frontmatter and improve local indexes rather than perform large rename-only churn.

## Why this structure

The Open Knowledge Format (OKF) blog announcement describes OKF v0.1 as a portable directory of markdown files with YAML frontmatter. It emphasizes plain markdown, plain files, queryable frontmatter fields, normal markdown links, optional `index.md`/`log.md` files, and one required concept field: `type`.

For this repo, those ideas map cleanly to the current wiki conventions:

| OKF idea | Local convention |
|---|---|
| Bundle | `docs/` |
| Concept document | Any non-archive markdown page that describes one topic, contract, feature, runbook, or report |
| Concept identity | Stable relative file path under `docs/` |
| Frontmatter | YAML block with at least `type`; recommended fields below |
| Links as graph | Relative markdown links between docs and canonical code artifacts |
| Reserved index/log pattern | Existing uppercase `INDEX.md` files and `log.md`; lowercase `index.md` is optional and should not replace existing hubs unless planned |
| Producer/consumer independence | Humans, agents, scripts, GitHub, and future OKF tools can read the same files |

## Frontmatter profile

Use this frontmatter on new living docs and on existing docs when making meaningful content edits:

```yaml
---
type: Technical Reference
title: Human-readable page title
description: One sentence explaining the page's purpose.
resource: technical/EXAMPLE.md
tags: [docs, backend]
timestamp: 2026-06-16T00:00:00Z
okf_version: 0.1
---
```

### Required field

- `type`: the document category or concept kind. Consumers must tolerate unknown values, so choose clear human-readable values.

### Recommended fields

- `title`: display title used by indexes and graph views.
- `description`: concise summary for search snippets and agent routing.
- `resource`: repo-relative path to the page or the primary code/config artifact it describes.
- `tags`: short lowercase tokens for filtering.
- `timestamp`: last meaningful documentation update in ISO-8601 UTC.
- `okf_version`: use `0.1` for pages updated under this profile.

## Type vocabulary

Prefer these type values unless a page needs a more specific one:

| Type | Use for |
|---|---|
| `Documentation Hub` | High-level entry points such as `README.md`, `ARCHITECTURE.md`, or folder hubs |
| `Documentation Index` | `INDEX.md` navigation pages |
| `Documentation Schema` | Wiki structure and maintenance rules |
| `Source-of-Truth Map` | Authority maps and canonical-source registries |
| `Technical Reference` | Stable API, schema, MCP, pipeline, model, and implementation references |
| `Runbook` | Operational procedures, diagnostics, troubleshooting, setup |
| `Guide` | User/operator walkthroughs |
| `Feature Spec` | Planned feature specs and implementation plans |
| `Implemented Feature` | Shipped behavior summaries |
| `Report` | Point-in-time audits, reviews, and investigations |
| `Archive` | Historical pages retained for traceability |

## Folder and index rules

1. Keep the existing folder taxonomy from [WIKI_SCHEMA.md](WIKI_SCHEMA.md).
2. Add or update the nearest uppercase `INDEX.md` whenever adding, removing, or materially moving a page.
3. Update the root [INDEX.md](INDEX.md) and [README.md](README.md) when the page is a new hub, canonical source, or high-value agent entry point.
4. Append a line to [log.md](log.md) for every wiki restructure.
5. Do not mass-rename files solely to satisfy lowercase `index.md` unless a separate migration plan updates every inbound link.

## Migration policy

- **Do now:** add frontmatter to edited living docs, keep hubs thin, and strengthen links to canonical sources.
- **Implemented:** automated OKF lint via `scripts/okf_lint.py` and combined `scripts/wiki_lint.py` (see [Automated lint](#automated-lint) below).
- **Avoid:** bulk-editing archived snapshots, changing URL-stable filenames without redirects, or duplicating canonical technical content in indexes.

## Official OKF reference

OKF v0.1 is specified in the [Google knowledge-catalog repository](https://github.com/GoogleCloudPlatform/knowledge-catalog/):

- [OKF SPEC v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) — conformance rules, reserved filenames, cross-linking.
- [OKF README](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/README.md) — format goals and reference producer/consumer tooling.

This repo does **not** depend on Google's `enrichment-agent` package. We adopt the spec and local lint tooling only.

## Vexlum profile vs OKF v0.1

| Topic | OKF v0.1 spec | Vexlum local profile |
|---|---|---|
| Required frontmatter | `type` only | `type`, `title`, `description`, `resource`, `tags`, `timestamp` (`vexlum` lint profile) |
| Hub / index files | Lowercase `index.md`, no frontmatter | Uppercase `INDEX.md` / `README.md` with frontmatter for agent routing |
| `resource` field | Canonical URI for underlying asset | Repo-relative path under `docs/` (also accepts `docs/<path>` for gallery parity) |
| `okf_version` | Optional on bundle-root `index.md` only | Recommended on materially updated concept pages |
| Activity log | Optional `log.md` | Required append-only [`log.md`](log.md); **no** frontmatter on log files |
| Archive snapshots | Not specified | Excluded from lint via `--exclude-prefix archive/` |

## Citations (OKF §8)

Reports and audits that cite external sources should add a `# Citations` section at the bottom of the page:

```markdown
# Citations

[1] [OKF SPEC v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
```

## Automated lint

From repo root (WSL or Windows Python with PyYAML):

```bash
# Backend docs — Vexlum profile (default); skip archived snapshots
python scripts/okf_lint.py --profile vexlum --exclude-prefix archive/

# OKF v0.1 minimal conformance (type + parseable frontmatter only)
python scripts/okf_lint.py --profile minimal --exclude-prefix archive/

# Sibling gallery bundle (from backend clone)
python scripts/okf_lint.py ../image-scoring-gallery/docs --profile vexlum --bundle-name docs

# Structural orphans/links + OKF metadata
python scripts/wiki_lint.py --exclude-prefix archive/

# CI-friendly JSON + non-zero exit on errors
python scripts/okf_lint.py --json --fail-on error --exclude-prefix archive/
```

Expect many `vexlum` warnings on backend living docs until they are touched opportunistically; archive paths are skipped by default.

### Continuous integration

GitHub Actions (backend [`.github/workflows/docs-lint.yml`](../.github/workflows/docs-lint.yml)):

- `pytest tests/test_okf_lint.py` — linter unit tests
- Full **gallery** bundle lint (checked out as sibling in the job)
- **Backend** changed-files lint via `scripts/ci/okf_lint_changed.py` (PR/push diffs only; does not block on legacy debt)

Gallery [`.github/workflows/test-and-contract.yml`](https://github.com/synthet/image-scoring-gallery/blob/main/.github/workflows/test-and-contract.yml) clones backend and runs full OKF lint on `docs/`.

## Agent workflow

When restructuring docs:

1. Read [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md) before changing contract, schema, API, phase, or cross-repo claims.
2. Use this OKF profile for metadata.
3. Prefer many small concept pages over a single duplicated mega-doc.
4. Link concepts with relative markdown links.
5. Keep [log.md](log.md) append-only.
