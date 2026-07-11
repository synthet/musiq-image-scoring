# /spec — Feature or change specification

Use when starting non-trivial work. Produce a **spec** the team can review before implementation.

## Inputs

- Problem statement or feature request (from user message or linked issue).
- Constraints: time, scope, tech stack (see **AGENTS.md**).

## Output

1. **Summary** — One paragraph.
2. **Users / stakeholders** — Who benefits.
3. **Non-goals** — What is explicitly out of scope.
4. **User stories** — Short "As a … I want … so that …" bullets.
5. **Acceptance criteria** — One **EARS-form** sentence per criterion (see below), numbered `AC-1`, `AC-2`, …
6. **Open questions** — Unknowns and decisions needed from humans.

## Acceptance criteria (EARS)

Write each criterion as a single EARS sentence so it is testable without interpreting intent:

- **Ubiquitous:** `The <system> shall <response>.`
- **Event-driven:** `When <trigger>, the <system> shall <response>.`
- **State-driven:** `While <state>, the <system> shall <response>.`
- **Unwanted behavior:** `If <condition>, then the <system> shall <response>.`
- **Optional feature:** `Where <feature is present>, the <system> shall <response>.`

Flag any criterion as **AMBIGUOUS** and ask for a rewrite before approval when it has:

- vague verbs ("handle", "support", "improve") with no observable outcome,
- more than one `shall` (split it into separate criteria), or
- an unclear subject (who/what responds?).

These IDs are the contract later verified by the `validate-implementation` skill.

## Done when

- Every criterion is one EARS sentence with a stable `AC-n` ID; none are marked AMBIGUOUS.
- Non-goals prevent scope creep.

## Optional

- Save to `specs/<feature-slug>.md` using `templates/spec-feature.md` if the repo uses that layout.
