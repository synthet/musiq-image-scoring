## Issue

<!-- REQUIRED. Link the backlog issue this PR closes. Format must trigger PR-close automation: -->
Closes #

> If this PR has no associated issue, stop and open one first — the canonical queue is the
> [Project board](https://github.com/users/synthet/projects/1). See
> [`docs/project/00-backlog-workflow.md`](../docs/project/00-backlog-workflow.md).

## Backlog hygiene

- [ ] Card moved to `Stage = Review` on the [Project board](https://github.com/users/synthet/projects/1)
- [ ] If cross-repo, the counterpart issue in `image-scoring-gallery` is linked above
- [ ] API contract / OpenAPI / `API.md` updated when REST behavior or paths changed
- [ ] Plan docs skimmed when track status changed: [`docs/planning/database/NEXT_STEPS.md`](../docs/planning/database/NEXT_STEPS.md), [`docs/features/planned/embeddings/NEXT_STEPS.md`](../docs/features/planned/embeddings/NEXT_STEPS.md)

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
- [ ] Spec-backed work: `validate-implementation` skill run; ACs Verified or open items listed
- [ ] If porting from synthet-code-framework: domain paths/commands adapted, not copied verbatim
- [ ] `python scripts/sync_assistant_trees.py --check` green when `.cursor/` or `.claude/` changed

## Skill files (`SKILL.md`) — only if this PR adds or materially changes agent skills

See [.agent/SKILL_CHANGE_AST10_REVIEW.md](../.agent/SKILL_CHANGE_AST10_REVIEW.md) and [.agent/SKILL_INVENTORY.md](../.agent/SKILL_INVENTORY.md).

- [ ] **AST10 sync:** `.cursor/skills/<name>/SKILL.md` is canonical; `.claude/skills/<name>/SKILL.md` updated in this PR where both exist
- [ ] **Inventory:** `.agent/SKILL_INVENTORY.md` updated (new skill row or **Last reviewed**)
- [ ] **Content review:** Full file read for prose + commands; description matches scope ([OWASP AST10 checklist](https://github.com/kenhuangus/agentic-skills-top-10/blob/main/checklist.md) — first-party subset in linked doc)
