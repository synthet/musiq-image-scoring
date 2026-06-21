> **Cursor:** Mirror: `.claude/commands/import-transcripts.md`.

# /import-transcripts — Mine Cursor chat history

Batch-import local Cursor agent transcripts into per-repo lesson staging (and optional backend raw-sessions). **Human review required** before promoting to `memory.md`.

## Steps

1. From **image-scoring-backend** repo root (Windows — transcripts live under `%USERPROFILE%\.cursor\projects`):

```powershell
python scripts/agent-memory/import_transcripts.py `
  --dry-run `
  --cursor-projects "$env:USERPROFILE\.cursor\projects" `
  --min-relevance 0.25
```

2. Review per-repo output:
   - Backend hub: `.agent/scratch/transcript-mining/<repo>/REVIEW.md`
   - Mirrored copy: `<repo>/.agent/scratch/transcript-mining/REVIEW.md` (gitignored)

3. **Tier A (backend only)** — write consolidated session + dream:

```powershell
python scripts/agent-memory/import_transcripts.py `
  --write-sessions `
  --repo image-scoring-backend `
  --cursor-projects "$env:USERPROFILE\.cursor\projects"
python scripts/agent-memory/dream.py
```

4. Review `dreams/*-changelog.md`; run `/promote-memory` or edit `memory.md` manually after deduping duplicates.

5. **Tier B/C repos** — curate `docs/LESSONS_LEARNED.md` from `REVIEW.md`; do not auto-commit personal paths.

## Flags

| Flag | Purpose |
|------|---------|
| `--repo NAME` | Filter to one repo folder name |
| `--min-relevance 0.25` | Skip off-topic / low-signal chats |
| `--no-consolidate` | One YAML per chat (not recommended) |
| `--no-mirror-staging` | Keep staging only under backend `.agent/scratch/` |

## Done when

- Summary report written (default: `.agent/scratch/transcript-mining/YYYY-MM-DD-report.md`)
- No secret patterns in candidates
- Human reviewed before any promote to tracked `memory.md`

## Skill

`.cursor/skills/agent-memory/SKILL.md`
