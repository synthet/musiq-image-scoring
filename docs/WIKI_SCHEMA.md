# Wiki Schema

Rules and conventions for LLM-maintained documentation in this project. This is the schema document — it tells the LLM how the wiki is structured and what workflows to follow.

---

## Core Principle

The LLM **writes and maintains** the wiki. The human curates sources, directs analysis, and asks questions. The wiki is a persistent, compounding artifact — knowledge is compiled once and kept current, not re-derived on every query.

---

## Architecture (Three Layers)

### 1. Raw Sources

Immutable input material the LLM reads but never modifies:

- Source code (`modules/`, `tests/`, `webui.py`, etc.)
- External documents dropped into `docs/raw/` (articles, papers, PDFs, images)
- Git history, issues, PR discussions
- User-provided files (via chat or file drops)

### 2. The Wiki

LLM-generated markdown files organized under `docs/`. The LLM owns this layer — it creates pages, updates them when new sources arrive, maintains cross-references, and keeps everything consistent. The human reads it; the LLM writes it.

### 3. This Schema

This document (`docs/WIKI_SCHEMA.md`) plus the wiki rules in `CLAUDE.md`. Together they tell the LLM how to operate. Co-evolved over time as conventions solidify.

---

## Page Types

| Type | Location | Naming | Purpose |
|------|----------|--------|---------|
| **Technical** | `docs/technical/` | `UPPER_SNAKE.md` | Implementation docs for existing features |
| **Plan/Proposal** | `docs/plans/<category>/` | `UPPER_SNAKE.md` | Specs for work not yet done |
| **Report** | `docs/reports/` | `UPPER_SNAKE.md` or `DATE_TITLE.md` | Analysis, research, reviews, summaries |
| **Guide** | `docs/getting-started/`, `docs/setup/`, `docs/gallery/` | `UPPER_SNAKE.md` | How-to for users/operators |
| **Reference** | `docs/reference/` | `UPPER_SNAKE.md` | API specs, model weights, data dictionaries |
| **Architecture** | `docs/architecture/` | `snake_case.md` | High-level design proposals |
| **Archive** | `docs/archive/` | original name | Deprecated/superseded pages (never delete — archive) |
| **Synthesis** | `docs/reports/` | `UPPER_SNAKE.md` | Cross-cutting analysis filed back from queries |
| **Raw Source** | `docs/raw/` | original filename | Immutable source documents |

---

## Conventions

### File Naming
- **Default:** `UPPER_SNAKE_CASE.md` (e.g., `DB_SCHEMA.md`, `CULLING_FEATURE.md`)
- **Date-stamped reports:** `TITLE_YYYY-MM-DD.md` or `YYYY_MM_DD_TITLE.md`
- **Numbered sequences:** `PREFIX_NN_TITLE.md` (e.g., `EMBEDDING_APP_01_OVERVIEW.md`)
- **Architecture proposals:** `snake_case.md` (existing convention in `docs/architecture/`)

### Document Structure
Every wiki page follows this structure:

```markdown
# Page Title

Brief description (1-2 sentences).

---

## Section Heading

Content...

### Subsection

Content...
```

Rules:
- **One `#` heading** per file (the title)
- **`##` for major sections**, `###` for subsections
- **Horizontal rule** (`---`) after the opening description
- **No YAML frontmatter** (Obsidian metadata goes in Dataview inline fields if needed)
- **Code blocks** use triple backticks with language hint (` ```python `, ` ```sql `, etc.)

### Linking
- **Relative paths** between docs: `[DB_SCHEMA.md](technical/DB_SCHEMA.md)`
- **Obsidian wikilinks** are acceptable in body text: `[[DB_SCHEMA]]`
- **Cross-folder links** use `../`: `[ARCHITECTURE.md](../technical/ARCHITECTURE.md)`
- **External links** use full URLs
- **Every page should have at least one inbound link** from an INDEX.md or another page

### Indexing
- **Every folder** has an `INDEX.md` with a table of its contents
- **`docs/INDEX.md`** is the master index — all pages should be reachable from it
- **Index entries** use the format: `| [FILENAME.md](FILENAME.md) | One-line description |`
- **Update indexes on every ingest** — never create a page without adding it to the relevant index

### Cross-References
- When a page mentions a concept, entity, or feature that has its own page, **link to it**
- When new information contradicts an existing page, **update the existing page** and note the contradiction
- When a page is superseded, **move it to `docs/archive/`** and update all inbound links

---

## Operations

### Ingest (`/wiki-ingest`)

Process a new source into the wiki. Flow:

1. **Read** the source document fully
2. **Discuss** key takeaways with the user (what's important, what to emphasize)
3. **Write** a summary page in the appropriate `docs/` subfolder
4. **Update** the relevant folder INDEX.md
5. **Update** `docs/INDEX.md` if adding to a new category
6. **Cross-reference** — update existing pages that relate to the new content:
   - Add links from existing pages to the new page
   - Add links from the new page to existing pages
   - Flag contradictions with existing content
7. **Log** the operation in `docs/log.md`

A single source may touch 5-15 wiki pages. Prefer one source at a time with user involvement.

### Query (`/wiki-query`)

Answer questions against the wiki. Flow:

1. **Read** `docs/INDEX.md` to find relevant pages
2. **Read** the relevant pages
3. **Synthesize** an answer with citations (`[Source](path)`)
4. **Optionally file** the answer as a new wiki page if it represents durable knowledge
5. **Log** the query in `docs/log.md`

Good answers that represent reusable analysis should be filed back as synthesis pages in `docs/reports/`.

### Lint (`/wiki-lint`)

Health-check the wiki. Look for:

- [ ] **Contradictions** — pages that disagree with each other
- [ ] **Stale claims** — information superseded by newer sources or code changes
- [ ] **Orphan pages** — no inbound links from any INDEX.md or other page
- [ ] **Missing pages** — concepts frequently mentioned but lacking their own page
- [ ] **Broken links** — references to pages that don't exist or have moved
- [ ] **Missing cross-references** — pages that should link to each other but don't
- [ ] **Index gaps** — pages that exist but aren't listed in any INDEX.md
- [ ] **Empty sections** — placeholder headings with no content
- [ ] **Data gaps** — questions the wiki should answer but can't yet

Output: a prioritized list of issues with suggested fixes. Apply fixes with user approval.

---

## Log Format

`docs/log.md` is an append-only chronological record. Each entry:

```markdown
## [YYYY-MM-DD] operation | Title

Brief description of what was done. Pages touched: [page1](path), [page2](path).
```

Operations: `ingest`, `query`, `lint`, `update`, `archive`, `create`.

The log is parseable: `grep "^## \[" docs/log.md | tail -10` shows the last 10 entries.

---

## What Not To Do

- **Never modify raw sources** in `docs/raw/`
- **Never delete wiki pages** — archive them instead
- **Never create a page without indexing it** — update the folder INDEX.md
- **Never leave broken cross-references** — if you move/rename a page, update all links
- **Never add YAML frontmatter** — the project doesn't use it
- **Never rewrite a page from scratch** when an update would suffice — prefer minimal diffs
- **Never create docs outside `docs/`** — the wiki lives in one place

---

## Evolving This Schema

This document is co-evolved by the human and LLM. When a convention proves wrong or a new page type emerges, update this schema. The schema should reflect how the wiki actually works, not how it was originally imagined.
