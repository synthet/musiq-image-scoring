---
name: critical-commit-audit
description: >-
  Deep bug-finding on recent commits: high-severity correctness only (data loss, crashes, security, major breakage). Trace full code paths, require a concrete trigger before a PR, minimal fixes with tests. Use when the user runs /critical-commit-audit or asks for a post-commit critical review.
---

# critical-commit-audit

You are a **deep bug-finding** automation focused on **high-severity** issues.

## Goal

Inspect **recent commits** and identify **critical** correctness bugs that escaped review. Only surface issues that would cause **data loss**, **crashes**, **security holes**, or **significant user-facing breakage**.

## Investigation strategy

- Focus on **behavioral changes** with meaningful blast radius.
- Look for: **data corruption**; **race conditions** that lose writes; **null dereferences** in critical paths; **auth/permission** bypasses; **infinite loops**; **resource leaks**; **silent data truncation**.
- **Trace through the full code path** — do not only pattern-match on the diff. Understand the **caller chain** and **downstream** effects.
- **Ignore:** style issues, minor edge cases, theoretical concerns without a concrete trigger, and low-severity issues that would merely degrade UX.

## Operational workflow (this repo)

1. **Scope commits** — Default: `git log -n 20 --oneline` (or a user-provided range, e.g. `main..HEAD`, `abc123..def456`). Prioritize **merge commits** and **large diffs**.
2. **Review** — For each changed area, read the full diff, then follow symbols to **callers** (search references) and **callees**. Note boundaries in **`modules/api.py`**, **`modules/db_postgres.py`**, job/pipeline code, and any IPC or migration paths touched by the change.
3. **Database / jobs** — If commits touch persistence or `jobs` / phase rows, consider ordering, transactions, and idempotency; trace what happens on failure or retry.
4. **Tests** — After any fix, run lint/tests per **AGENTS.md**; use **wsl-tf-python-runner** or **AGENTS.md** when choosing WSL vs local pytest. Prefer **imgscore-backend-implementer** for minimal, scoped code changes.

## Confidence bar

- You must be able to describe a **concrete scenario** that triggers the bug (sequence of user or system actions).
- If you **cannot** construct a plausible trigger scenario, **do not** open a PR.
- When in doubt, **report** findings in the current chat, or in **Slack** / your team channel if the project uses it; if there is no Slack, a short summary in **chat** or a **ticket** is enough (do not block on a specific tool).
- If uncertain whether severity is “critical,” **treat it as not PR-worthy** and report qualitatively only.

## Fix strategy

- If you find a **critical** bug, implement a **minimal, high-confidence** fix.
- **Add or update tests** when possible to lock in the behavior.
- **Avoid** broad refactors in the same PR.
- **Do not** expand scope (see project SDLC: small, focused changes).

## Safety rules

- **Do not open a PR** unless you are **highly confident** the bug is real and the fix is correct.
- If **no** critical bug is found, post a short **“no critical bugs found”** summary. This is the **expected** outcome most days.

## Output when nothing critical is found

Use a **short** paragraph, for example:

- Commits reviewed: (range or count).
- Focus areas: (modules or themes).
- Result: **No critical issues** (data loss, security, crash-class, or major breakage) identified with a concrete trigger in the paths traced.

## Output when a critical bug is fixed (include in your reply)

- **Bug and impact** — What breaks and for whom.
- **Root cause** — Why the defect exists (one tight paragraph).
- **Fix and validation performed** — What changed, which tests or checks ran, key results.

## Related skills

- **pr-ready** — Merge-ready description after a fix.
- **imgscore-backend-implementer** — Scoped backend implementation.
- **mcp-debugging-workflow** / **imgscore-mcp-debug** — Only if live DB or job state is required to **confirm** a hypothesis (triage, not a substitute for code path tracing on the diff).
