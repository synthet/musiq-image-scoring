# /pr-ready — Prepare for pull request

Use when implementation is complete and you want a merge-ready PR.

## Inputs

- Diff or branch state; **AGENTS.md**; optional issue link.

## Output

1. **Summary** — User-facing description of the change (not the commit list).
2. **Risk / rollout** — Breaking changes, migrations, config.
3. **Testing** — Commands run and results.
4. **Suggested commit message** — Prefer [Conventional Commits](https://www.conventionalcommits.org/); use skill `commit-conventions` if present.
5. **PR description** — Paste-ready Markdown; align with `templates/pull_request_template.md` if the repo uses it.

## Self-review

- Scan diff for **debug code**, **TODOs** that should be issues, and **accidental files**.
- Confirm no secrets or large binaries.

## Done when

- Maintainer can open a PR without rewriting the description.

## Optional

- For long-running PR hygiene (comments, CI loops), use a dedicated “babysit PR” skill in your personal `~/.cursor/skills/` if configured.
