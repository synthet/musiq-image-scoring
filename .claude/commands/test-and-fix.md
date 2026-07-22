# /test-and-fix — Run tests and repair failures

Use when CI is red, tests fail locally, or the user asks for a test pass.

## Compiled bootloader (do this first)

```powershell
python scripts/agent_skills/test_and_fix.py run
# After fixes:
python scripts/agent_skills/test_and_fix.py run --failed-only
# Narrow path (args after -- go to pytest):
python scripts/agent_skills/test_and_fix.py run -- tests/test_foo.py
# Optional Markdown report:
python scripts/agent_skills/test_and_fix.py report --from-state -o .agent/scratch/test-fix.md
```

Prefer `--wsl` when matching the WebUI env (`~/.venvs/tf`). Do **not** rediscover the fast pytest marker expression — the harness owns it.

## Ownership split

| Owner | Responsibility |
|-------|----------------|
| **Code** | Run canonical fast subset, parse failures, fingerprint, re-run failed nodeids |
| **LLM** | Root-cause + minimal code/test fix; decide blocker vs keep repairing |
| **Human** | Approve weakening assertions or skipping tests |

## Inputs

- Failing log output if available (otherwise start with `run`).
- Integration / Postgres / Docker E2E only when the user asked for that suite (see AGENTS.md Pytest E2E vocabulary).

## Loop

1. Run the harness (`run`).
2. For each failure in the JSON: locate root cause, fix **minimal** code or test expectation.
3. `run --failed-only` until green or blocked; if blocked, document owner/next step.

## Done when

- Harness reports `ok: true`, or there is a clear written blocker.

## Avoid

- Disabling tests or weakening assertions without explicit user approval.

## Related

- [`.agent/SKILL_COMPILATION.md`](../.agent/SKILL_COMPILATION.md)
- Skill: `agent-dev-tooling` for WSL / doctor / full command list
