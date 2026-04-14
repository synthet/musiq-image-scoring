# /wiki-lint — Health-check the docs wiki

Audit the wiki for structural problems, stale content, and missed connections. Keep the knowledge base healthy as it grows.

## Schema

Read `docs/WIKI_SCHEMA.md` for conventions and the full lint checklist.

## Steps

1. **Scan all INDEX.md files** — build a list of every page referenced in indexes.
2. **Scan all .md files in `docs/`** — build a list of every page that exists on disk.
3. **Compare** to find:
   - **Orphan pages** — exist on disk but not in any INDEX.md
   - **Broken index entries** — listed in INDEX.md but file doesn't exist
   - **Broken links** — `[text](path)` references to non-existent files
4. **Check cross-references** — for each page, verify it has at least one inbound link.
5. **Check for stale content** (sample 10-15 pages):
   - Compare claims against current code (e.g., does the API endpoint still exist?)
   - Flag pages that reference removed features or outdated versions
6. **Check for missing pages** — scan for concepts frequently mentioned across pages that lack their own dedicated page.
7. **Check for contradictions** — look for pages that make conflicting claims about the same topic.
8. **Present findings** as a prioritized report:

```markdown
## Wiki Lint Report — YYYY-MM-DD

### Critical (broken references)
- ...

### Structural (orphans, missing indexes)
- ...

### Stale (outdated content)
- ...

### Suggestions (missing pages, new connections)
- ...
```

9. **Ask the user** which fixes to apply.
10. **Apply approved fixes** and update `docs/log.md`: `## [YYYY-MM-DD] lint | Wiki health check`

## Scope Control

- **Quick lint** (default): Steps 1-4 only (structural checks). Fast, no content reading.
- **Full lint**: All steps including content staleness and contradiction checks. Slower, reads many pages.
- User can specify: `/wiki-lint quick` or `/wiki-lint full`

## Done when

- Report presented to user.
- Approved fixes applied.
- Log entry appended.
