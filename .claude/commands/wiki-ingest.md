> **Cursor:** Same intent as Claude `/wiki-ingest`. When customizing, keep in sync with `.claude/commands/wiki-ingest.md`.

# /wiki-ingest — Process a source into the wiki

Ingest a new source document (article, paper, report, code analysis, or user-provided file) into the docs wiki. The wiki is a persistent, compounding knowledge base — each ingest updates multiple pages.

## Inputs

- Source document: file path, URL, or pasted content from the user message.
- User guidance on what to emphasize (optional).

## Schema

Read `docs/OKF_ADOPTION.md` and `docs/WIKI_SCHEMA.md` for OKF metadata and conventions, page types, and linking rules before proceeding.

## Compiled bootloader (glue — run these; do not re-invent formats)

```powershell
# After choosing type/path/title (LLM judgment):
python scripts/agent_skills/wiki_scaffold.py frontmatter `
  --type "Report" --title "…" --resource reports/FOO.md `
  -o docs/reports/FOO.md --body "# …`n`n"

python scripts/agent_skills/wiki_scaffold.py append-index docs/reports/INDEX.md `
  --link FOO.md --desc "One-line description"

python scripts/agent_skills/wiki_scaffold.py append-log --verb ingest --title "…" --body "…"

python scripts/agent_skills/wiki_scaffold.py lint
```

## Ownership split

| Owner | Responsibility |
|-------|----------------|
| **Code** | Frontmatter stub, INDEX row, log append, OKF lint |
| **LLM** | Source summary, page body, type/location, cross-links |
| **Human** | Review before treating ingest as done |

## Steps (judgment)

1. **Read the source** in full. If it's a URL, fetch it. If it's a file, read it.
2. **Summarize key takeaways** to the user (3-5 bullets). Ask what to emphasize before writing.
3. **Determine page type and location** per the schema.
4. **Write the summary page** (use `frontmatter` harness for OKF header; draft prose yourself).
5. **Update INDEX.md** via `append-index` (folder + root `docs/INDEX.md` when needed).
6. **Cross-reference** related pages (bidirectional links — LLM).
7. **If the source is a file**, copy or move it to `docs/raw/` (immutable archive).
8. **Append to `docs/log.md`** via `append-log`.
9. **Lint** via `wiki_scaffold.py lint`.

## Done when

- Summary page exists in the correct location.
- Relevant INDEX.md files updated.
- Cross-references added when related pages exist.
- Log entry appended; lint clean (or findings explained).
- User has reviewed the summary.

## Skill

Backend wiki conventions: [`.cursor/skills/docs-wiki/SKILL.md`](../skills/docs-wiki/SKILL.md) and rule [`.cursor/rules/documentation.mdc`](../rules/documentation.mdc).
Compilation: [`.agent/SKILL_COMPILATION.md`](../../.agent/SKILL_COMPILATION.md).
