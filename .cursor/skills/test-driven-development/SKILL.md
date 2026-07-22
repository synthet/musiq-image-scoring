---
name: test-driven-development
description: >-
  Use when implementing a feature, bug fix, refactor, or behavior change that can
  be tested. Apply before production code changes to enforce red-green-refactor,
  prove tests fail for the intended reason, and keep implementation minimal. Also
  use for risky vertical slices or when the user asks for TDD, red/green/refactor,
  or tests first.
---

# Test-driven development

## Purpose

Use tests to define expected behavior before changing production code. A passing test that never
failed does not prove the behavior is covered. Prefer short feedback loops so agent edits stay grounded
in executable evidence rather than broad speculative changes.

## When to use

- Adding behavior where a unit, integration, CLI, or snapshot test can observe the outcome.
- Fixing a bug that should never regress.
- Refactoring behavior behind an existing public seam.
- Any change where the user asks for TDD, red/green/refactor, or tests first.

Do **not** force TDD for pure documentation, mechanical formatting, generated asset sync, or when the
repo has no practical test seam. State the limitation and choose the closest verification.

## Repo test commands

Prefer documented runners in **AGENTS.md**:

- Backend: WSL + `~/.venvs/tf` or `image-scoring-tests`; fast subset
  `pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py`
- Gallery: `npm run test:run`, `npx tsc --noEmit`, `npx tsc -p electron/tsconfig.json --noEmit`

## Use with

- `systematic-debugging` when a bug's root cause is not yet known.
- `verification-before-completion` before claiming the implementation is complete.

## Workflow

1. **Choose one vertical slice.** Name the externally visible behavior and the smallest seam that
   can verify it.
2. **RED — write one failing test.** Name the behavior clearly, exercise public contracts and real
   code where practical, and keep one assertion focus. For bug fixes, reproduce the reported symptom.
3. **Verify RED.** Run the smallest relevant test command. Confirm it fails for the intended reason,
   not typos, imports, fixtures, or setup. If it passes immediately, rewrite it.
4. **GREEN — implement the minimum.** Write only enough production code to pass. Do not add
   unrequested options, abstractions, cleanup, or drive-by edits.
5. **Verify GREEN.** Re-run the targeted test. Fix production code rather than weakening the test.
6. **REFACTOR — improve while green.** Remove duplication or clarify names only after GREEN. Do not
   add behavior during refactor.
7. **Widen.** Repeat for the next slice, then run the surrounding package/module tests or the
   documented fast suite.

## Output

```markdown
## TDD Log
- Behavior slices:
- RED test:
- RED command and failure:
- GREEN change:
- GREEN command and pass:
- Refactor notes:
- Broader verification:
```
