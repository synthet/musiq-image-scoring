# /plan — Implementation plan

Use after a spec exists (or for small tasks, a verbal agreement). Prefer **plan mode** or explicit user approval before large edits.

## Inputs

- Approved spec or tight task description.
- Relevant files the user pointed at.

## Output (Implementation Plan)

1. **Goal** — What "done" means.
2. **Files / areas to touch** — Paths or components.
3. **Approach** — Steps in order; call out risky changes.
4. **Failing test stubs to write BEFORE touching implementation** — Specific test names, files, and assertions that must be written first and confirmed failing.
5. **Rollback / flags** — If feature-flagged or migratory.

## Done when

- Another developer could execute the plan without guessing.
- Failing test stubs are identified and ready to write before implementation begins.

## Note

If the user has not approved implementation, **do not** apply code changes until they confirm.
