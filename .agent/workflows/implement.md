# /implement — Execute an approved plan

Use when the user has approved a plan or given a small, explicit task.

## Inputs

- Approved plan or task list.
- [AGENTS.md](file:///d:/Projects/image-scoring-backend/AGENTS.md) for lint/test/build commands.

## Steps

1. **Write failing test stubs** from the plan's "Failing test stubs" section; run them and confirm they fail.
2. **Implement** in minimal diffs, matching existing style, until the stubs pass.
3. Run **lint** and **tests** from [AGENTS.md](file:///d:/Projects/image-scoring-backend/AGENTS.md); fix failures.
4. Summarize what changed and where.

## Done when

- Test stubs were written and confirmed failing before implementation began.
- All agreed items are implemented.
- Tests pass after implementation.
- Lint passes (or failures explained with next steps).

## Checklist

- [ ] Test stubs written and failing before implementation began
- [ ] Tests pass after implementation
- [ ] No unrelated refactors
- [ ] No secrets committed
- [ ] [AGENTS.md](file:///d:/Projects/image-scoring-backend/AGENTS.md) commands run (or documented why not)
