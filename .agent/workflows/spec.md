# /spec — Feature or change specification

Use when starting non-trivial work. Produce a **spec** the user can review before implementation.

## Inputs

- Problem statement or feature request.
- Constraints: time, scope, tech stack (see [AGENTS.md](file:///d:/Projects/image-scoring-backend/AGENTS.md)).

## Steps

1. **Research** the context of the requested change.
2. **Draft the Spec** containing:
    - **Summary**: One paragraph.
    - **Users / stakeholders**: Who benefits.
    - **Non-goals**: What is explicitly out of scope.
    - **User stories**: Short "As a ... I want ... so that ..." bullets.
    - **Acceptance criteria**: Checkable bullets (Given/When/Then or "When X, then Y").
    - **Open questions**: Unknowns and decisions needed from humans.
3. **Present to User** for approval before moving to `/plan`.

## Done when

- Criteria are testable without interpreting intent.
- Non-goals prevent scope creep.
