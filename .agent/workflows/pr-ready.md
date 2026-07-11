# /pr-ready — Prepare for pull request

Use when implementation is complete and you want a merge-ready PR.

## Inputs

- Diff or branch state; [AGENTS.md](../AGENTS.md).
- Validation report from `validate-implementation` if a spec with acceptance criteria exists.

## Output (PR Ready Report)

1. **Summary** — User-facing description of the change (not the commit list).
2. **Risk / rollout** — Breaking changes, migrations, config.
3. **Testing** — Commands run and results.
4. **Suggested commit message** — Prefer Conventional Commits.
5. **PR description** — Paste-ready Markdown.

## Definition of done

- Lint/test commands from **AGENTS.md** ran and are green.
- Spec ACs are Verified per `validate-implementation`, or open Unknowns/Failures are listed explicitly.
- PR references its issue (`Closes #<N>`) and the board card is in `Stage = Review`.

## Done when

- Maintainer can open a PR without rewriting the description.
