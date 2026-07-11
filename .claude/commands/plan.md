# /plan — Implementation plan

Use after a spec exists (or for small tasks, a verbal agreement). Prefer **plan mode** or explicit user approval before large edits.

## Inputs

- Approved spec or tight task description.
- Relevant files the user pointed at.
- Authority stack: **docs/CANONICAL_SOURCES.md** for API/schema/phase contracts.

## Output

1. **Goal** — What "done" means.
2. **Files / areas to touch** — Paths or components.
3. **Approach** — Steps in order; call out risky changes.
4. **Tests** — Failing test stubs to write *before* touching implementation, derived from spec
   acceptance criteria (`AC-n`). List the test file paths and the assertion names.
5. **Rollback / flags** — If feature-flagged or migratory.

## Done when

- Another developer could execute the plan without guessing.
- Failing test stubs (step 4) are identified and ready to write before implementation begins.
- Test plan matches project conventions (see **AGENTS.md** — fast pytest subset vs Postgres API E2E vs Docker inference E2E).

## Note

If the user has not approved implementation, **do not** apply code changes until they confirm.
