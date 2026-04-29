## Backlog / docs checklist

- [ ] Root [`TODO.md`](TODO.md) updated if open items changed (checkboxes, **Last evaluated**, counts, **Highest-Impact Next Steps** if order changed)
- [ ] Related plan docs skimmed: [`docs/planning/database/NEXT_STEPS.md`](docs/planning/database/NEXT_STEPS.md), [`docs/features/planned/embeddings/NEXT_STEPS.md`](docs/features/planned/embeddings/NEXT_STEPS.md) when track status changed
- [ ] API contract / OpenAPI / `API.md` updated when REST behavior or paths changed
- [ ] If **image-scoring-gallery** is affected: note in PR body + sync per [`docs/project/00-backlog-workflow.md`](docs/project/00-backlog-workflow.md) sync order

## Summary

**What changed:**

## Motivation

<!-- Why is this change needed? Link issues: Fixes # -->

## How to test

<!-- Commands or steps; match AGENTS.md and CLAUDE.md -->

**Risk / testing notes:**

## Risk / rollout

<!-- Breaking changes, migrations, feature flags, downtime -->

## SDLC checklist (agent-sdlc)

- [ ] Tests added or updated as needed
- [ ] Lint / typecheck pass
- [ ] No secrets or credentials in code
- [ ] Docs updated if behavior is user-visible

## Skill files (`SKILL.md`) — only if this PR adds or materially changes agent skills

See [.agent/SKILL_CHANGE_AST10_REVIEW.md](../.agent/SKILL_CHANGE_AST10_REVIEW.md) and [.agent/SKILL_INVENTORY.md](../.agent/SKILL_INVENTORY.md).

- [ ] **AST10 sync:** `.cursor/skills/<name>/SKILL.md` is canonical; `.claude/skills/<name>/SKILL.md` updated in this PR where both exist
- [ ] **Inventory:** `.agent/SKILL_INVENTORY.md` updated (new skill row or **Last reviewed**)
- [ ] **Content review:** Full file read for prose + commands; description matches scope ([OWASP AST10 checklist](https://github.com/kenhuangus/agentic-skills-top-10/blob/main/checklist.md) — first-party subset in linked doc)
