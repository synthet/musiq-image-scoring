---
name: commit-and-push
description: >-
  Use when the user asks to commit and push, publish, ship, or prepare a release
  commit. Guides staging only intended changes, writing a Conventional Commit,
  committing, and pushing to origin after verifying status and diff.
---

# Commit and push (compiled harness)

Ship local work only when the user explicitly asks. Pair with `release-bump` when
`modules/version.py` / `CHANGELOG.md` were promoted.

## Invoke

```bash
# Dry-run inspect (default)
python scripts/agent_skills/commit_and_push.py --json

# Release prep: list + run agent-infra verify
python scripts/agent_skills/commit_and_push.py --release --run-verify --json

# Only after explicit user request to commit/push:
python scripts/agent_skills/commit_and_push.py \
  --execute --commit -m "feat(scope): summary" --json
python scripts/agent_skills/commit_and_push.py --execute --push --json
```

## LLM judgment slots

- Draft Conventional Commit subject/body (`commit-conventions`).
- Prefer explicit path staging when unrelated dirty files exist (inspect `paths` first).

## Human / safety (enforced)

- Harness **defaults to dry-run**; `--execute` required for commit/push.
- Secret-looking paths (`.env`, `secrets.json`, keys) block staging.
- Never modify `.git/config`, never `--no-verify` unless user asked.
- Never force-push `main`/`master` unless user asked.
- Do not amend after a failed hook — new commit instead.
