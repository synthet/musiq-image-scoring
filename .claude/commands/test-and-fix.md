# /test-and-fix — Run tests and repair failures

Use when CI is red, tests fail locally, or the user asks for a test pass.

## Inputs

- **AGENTS.md** — canonical test commands.
- Failing log output or error messages if available.

## Steps

1. Run the **unit test** command from AGENTS.md (then integration/E2E if relevant).
2. For each failure: locate root cause, fix **minimal** code or test expectation.
3. Re-run until green or blocked; if blocked, document what is needed (data, env, flaky test).

## Done when

- Tests pass, or there is a clear written blocker with owner/next step.

## Avoid

- Disabling tests or weakening assertions without explicit user approval.
