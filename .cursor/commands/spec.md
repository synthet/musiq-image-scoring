# /spec — Feature or change specification

Use when starting non-trivial work. Produce a **spec** the team can review before implementation.

## Inputs

- Problem statement or feature request (from user message or linked issue).
- Constraints: time, scope, tech stack (see **AGENTS.md**).

## Output

1. **Summary** — One paragraph.
2. **Users / stakeholders** — Who benefits.
3. **Non-goals** — What is explicitly out of scope.
4. **User stories** — Short “As a … I want … so that …” bullets.
5. **Acceptance criteria** — Checkable bullets (Given/When/Then or “When X, then Y”).
6. **Open questions** — Unknowns and decisions needed from humans.

## Done when

- Criteria are testable without interpreting intent.
- Non-goals prevent scope creep.

## Optional

- Save to `specs/<feature-slug>.md` using `templates/spec-feature.md` if the repo uses that layout.
