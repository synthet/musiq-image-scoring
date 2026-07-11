# /critical-commit-audit — Deep review of recent commits for critical bugs

Use when you want a **high-severity-only** pass over **recent git history** (data loss, crashes, security, major breakage).

## Instructions

1. **Read the skill** [`.cursor/skills/critical-commit-audit/SKILL.md`](../skills/critical-commit-audit/SKILL.md) and follow it end to end.
2. **Use AGENTS.md** for lint, pytest, and environment commands after any code change.

## Inputs

- Optional **commit range** (e.g. `main..HEAD`, `~10`, `abc..def`). Default: last **20** commits (see skill).

## Output

- Per skill: either a **“no critical bugs found”** short summary, or **Bug and impact** / **Root cause** / **Fix and validation** if you fixed a critical issue and are opening a PR.

## Done when

- Commits in scope are reviewed with **call-path** tracing, not only diff skimming.
- **No PR** is opened without a **concrete trigger** scenario and high confidence (per skill).
