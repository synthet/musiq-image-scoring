# /implement — Execute an approved plan

Use when the user has approved a plan or given a small, explicit task.

## Inputs

- Approved plan or task list.
- **AGENTS.md** for lint/test/build commands.

## Steps

1. Implement in **minimal diffs**; match existing style.
2. Add or update tests when behavior changes.
3. Run **lint** and **tests** from AGENTS.md; fix failures.
4. Summarize what changed and where.

## Done when

- All agreed items are implemented.
- Lint and tests pass (or failures are explained with next steps).

## Checklist

- [ ] No unrelated refactors
- [ ] No secrets committed
- [ ] AGENTS.md commands run (or documented why not)
