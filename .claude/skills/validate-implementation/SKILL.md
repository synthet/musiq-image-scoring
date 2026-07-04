---
name: validate-implementation
description: Verify an implementation against its spec's acceptance criteria, marking each AC Verified, Failed, or Unknown with concrete evidence. Use after /implement or /test-and-fix, before /pr-ready, or when the user asks whether the spec is actually satisfied.
---

# Validate implementation against spec

Answers one question: **does the implementation satisfy the spec's acceptance criteria?**
This is *not* merge readiness — CI status, review hygiene, and issue linkage belong to `/pr-ready`
(definition of done). Keep the two checks separate.

## Inputs

- The spec with numbered `AC-n` acceptance criteria (from `/spec`). If no spec exists, reconstruct
  the criteria from the issue/user request and confirm them with the user first.
- The current diff/branch state and the project's test commands from **AGENTS.md**.

## Procedure

For **each** acceptance criterion, assign exactly one verdict:

| Verdict | Meaning | Required evidence |
|---------|---------|-------------------|
| **Verified** | Observed behavior matches the criterion | A test run, command output, or reproducible manual check — cite the command and result |
| **Failed** | Observed behavior contradicts the criterion | The failing output or observed divergence |
| **Unknown** | Could not be checked in this environment | Why it could not be checked and what would be needed |

Rules:

- **Evidence or it didn't happen.** "Looks done", "should work", or "probably green" are not
  verdicts. Reading the code is supporting context, not sufficient evidence on its own — prefer
  running the narrowest relevant test or command.
- **Unknown is never an implicit pass.** Report Unknowns explicitly; the user decides whether they
  block. Do not round Unknown up to Verified.
- **Do not weaken the criteria.** If an AC turns out to be untestable as written, flag it and
  propose a rewrite — do not quietly substitute a weaker check.
- **Minimal fixes only.** If an AC fails and the fix is obvious and small, fix it and re-verify;
  otherwise report the failure.

## Output

```
## Validation report — <spec/feature name>

| AC | Criterion (short) | Verdict | Evidence |
|----|-------------------|---------|----------|
| AC-1 | … | Verified | `pytest tests/test_x.py::test_y` passed |
| AC-2 | … | Unknown  | needs staging credentials |

Overall: N verified / N failed / N unknown. <Blockers or next steps.>
```

Only claim the spec is satisfied when **every** AC is Verified.
