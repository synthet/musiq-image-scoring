# /pr-ready — Prepare for pull request

Use when implementation is complete and you want a merge-ready PR.

## Inputs

- Diff or branch state; [AGENTS.md](file:///d:/Projects/image-scoring-backend/AGENTS.md).

## Output (PR Ready Report)

1. **Summary** — User-facing description of the change (not the commit list).
2. **Risk / rollout** — Breaking changes, migrations, config.
3. **Testing** — Commands run and results.
4. **Suggested commit message** — Prefer Conventional Commits.
5. **PR description** — Paste-ready Markdown.

## Done when

- Maintainer can open a PR without rewriting the description.
