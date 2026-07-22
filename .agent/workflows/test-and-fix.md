# /test-and-fix — Run tests and repair failures

Use when CI is red, tests fail locally, or the user asks for a test pass.

## Compiled bootloader

```powershell
python scripts/agent_skills/test_and_fix.py run
python scripts/agent_skills/test_and_fix.py run --failed-only
```

See [`.cursor/commands/test-and-fix.md`](../.cursor/commands/test-and-fix.md) for ownership split and loop.
Inputs: [AGENTS.md](../AGENTS.md) (canonical suites); failing logs if available.

## Done when

- Harness `ok: true`, or a clear written blocker.

## Avoid

- Disabling tests or weakening assertions without explicit user approval.
