# /pr-ready — Prepare for pull request

Use when implementation is complete and you want a merge-ready PR.

This is the **definition-of-done** check: merge readiness (checks green, hygiene, issue linkage).
Spec satisfaction is separate — run `validate-implementation` first for per-criterion verification.

## Compiled bootloader (do this first)

```powershell
python scripts/agent_skills/pr_ready_checks.py scan --run-lint --run-tests
python scripts/agent_skills/pr_ready_checks.py skeleton --issue <N> -o .agent/scratch/pr.md
```

Fix any `error` findings from `scan` before writing narrative. Fill Summary / Motivation in the
skeleton (LLM judgment). Do not open/push a PR unless the user asked.

## Inputs

- Diff or branch state; **AGENTS.md**; optional issue link.
- Validation report from `validate-implementation` if a spec with ACs exists.

## Output

1. **Summary** — User-facing description of the change (not the commit list).
2. **Risk / rollout** — Breaking changes, migrations, config.
3. **Testing** — Commands run and results (cite `pr_ready_checks` / pytest output).
4. **Suggested commit message** — Prefer Conventional Commits; use `commit-conventions` if present.
5. **PR description** — Paste-ready Markdown from the skeleton; align with `.github/pull_request_template.md`.

## Self-review

- Scan diff for **debug code**, **TODOs** that should be issues, and **accidental files**.
- Confirm no secrets or large binaries (`scan` covers common secret patterns).

## Definition of done

- Lint/test commands from **AGENTS.md** ran and are green (state actual results; never "probably green").
- Spec ACs are Verified per `validate-implementation`, or open Unknowns/Failures are listed explicitly.
- PR references its issue (`Closes #<N>`) and the board card is in `Stage = Review`.
- Diff is clean: no debug code, secrets, large binaries, or unrelated refactors.

## Done when

- Maintainer can open a PR without rewriting the description.

## Related

- [`.agent/SKILL_COMPILATION.md`](../.agent/SKILL_COMPILATION.md)
- Skill: `validate-implementation`
