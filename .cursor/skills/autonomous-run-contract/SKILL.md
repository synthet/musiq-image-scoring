---
name: autonomous-run-contract
description: >-
  Use before letting an agent run without step-by-step supervision — unattended
  or overnight runs, long scoring/backfill jobs, "keep iterating until it
  passes", ratchet loops, subagent fan-out, or swarm work. Also use to decide how
  much orchestration a task needs (single call vs loop vs chain vs parallel vs
  DAG). Produces a written contract with metric, budget, revert rule, and stop
  conditions before the run starts.
---

# Autonomous run contract

Supervised work is governed by the `/spec → /plan → /implement` loop. **Unattended** work is not —
nobody reads the intermediate steps, so the constraints have to be written down before the run
starts. This skill produces that contract.

The premise: the bottleneck in an autonomous run is rarely the next model call. It is where memory
and evaluation live. A loop remembers only the current state; durable history, a visible metric, and
a revert path are what make repeated iteration converge instead of drift.

## When to use

- "Run it overnight", "keep going until the tests pass", "iterate on this without asking me"
- Long-running scoring, backfill, embedding, or migration jobs that mutate the database
- Fan-out across many files, folders, or hypotheses, or spawning several subagents
- Deciding whether a task even needs orchestration beyond a single call

## Gate — can success be verified?

If there is no test, metric, rubric, or source requirement that separates better from worse, **stop
and define one, or keep the human in the loop**. Autonomy without a verifiable signal produces
activity, not progress. Say this plainly rather than starting the run.

Then confirm the other three loop preconditions:

- **Reversible** — every step can be undone (`git reset` to the last retained commit; for DB work, a
  verified backup via `backup-db` and a tested restore path *before* the run, not after).
- **Short horizon** — one iteration finishes fast enough to give frequent feedback.
- **Bounded environment** — the action space is narrowed by scope, not by hope.

## Step 1 — Pick the smallest architecture that fits

| Situation | Start with | Why |
|-----------|-----------|-----|
| Simple, low-risk question | Single call | Lowest latency; no machinery to debug |
| Output can be checked | **Loop** (generate → evaluate → revise) | Repeated feedback improves the artifact |
| Steps are stable and ordered | Chain | Predictable, testable stages |
| Clear input categories | Router | Separates policies per category |
| Subtasks are independent | Parallel fan-out | Reduces wall-clock time |
| Decomposition varies per run | Orchestrator + workers | Dynamic specialization |
| Alternatives must stay alive | Branches / worktrees | Preserves lineage instead of forcing one winner |
| Facts must survive the session | Persisted artifacts, DB rows, `.agent-memory/` | Transcript summaries are not memory |

Escalate a level only when the current one has demonstrably failed. More agents increase activity and
opacity before they increase quality.

## Step 2 — Write the run contract

Before the first iteration, state all of these in the task thread (or a scratch file under
[`.agent/scratch/`](../../../.agent/scratch/)). This is the natural-language program the run executes:

- **Objective** — one sentence, testable.
- **Mutable files** — what the run may edit.
- **Protected** — what it may not touch. In this repo that always includes DB migrations under
  `alembic/`, the API contract, and the test fixtures the metric depends on.
- **Metric and direction** — the exact command and the number or verdict it produces. Use the real
  gates from [`.agent/COMMANDS.md`](../../../.agent/COMMANDS.md): the fast pytest subset,
  `ruff check <paths>`, `python scripts/doctor.py --json`.
- **Run command** — how one iteration is executed and how its output is parsed. Note the WSL + venv
  requirement for anything touching `modules.*`, the DB, or ML.
- **Keep-or-revert rule** — improvement is retained as a commit; regression or crash is reverted.
- **Crash policy** — fix if mechanical, else revert and record; never leave the tree dirty.
- **History** — where each iteration's parent state, change, metric, and verdict are recorded.
- **Escalation** — the conditions that require a human (see below).
- **Exhaustion** — what "no more ideas" looks like, so the run stops instead of churning.

## Step 3 — Declare a budget

No unattended run starts without explicit limits. State the ones that apply:

| Limit | Example |
|-------|---------|
| Iterations / model calls | 20 iterations |
| Concurrent workers, total workers | 4 concurrent, 24 total |
| Wall-clock | 90 minutes |
| Retries per failure | 2, then revert |
| Rows / images / folders touched | cap the batch; do not let a backfill run unbounded |
| Minimum evidence to finalize | fresh green output from the metric command per retained change |

When a budget is exhausted, **return the best current artifact, the completed work, the unresolved
issues, and the reason for stopping.** Do not hide partial failure behind a fluent summary — that is
the same honesty rule as
[`verification-before-completion`](../verification-before-completion/SKILL.md), applied to the run as
a whole.

## Step 4 — Ratchet, one change at a time

Each iteration: inspect state → propose **one** motivated change → apply → evaluate → keep or revert
→ record. One change per iteration is what makes the metric attributable; batching changes destroys
the signal that justifies keeping them.

Two failure modes to guard against:

- **The metric is gamed.** A ratchet improves only what it can see. Carry the constraints that are not
  in the metric (runtime, VRAM, DB size, public API shape, security) as revert conditions, not as
  hopes.
- **Judgment gets frozen into rules.** If a step needs a heuristic to stay correct, it stays with the
  model — the same boundary [`/compile-skill`](../../commands/compile-skill.md) draws for harnesses.

## Fan-out extras

- **Define the reducer before the fan-out.** Decide how findings will be merged, deduplicated, and
  ranked before any worker starts; otherwise you get N reports and no answer.
- **Every handoff is an artifact contract.** Workers return structured findings with evidence, not
  prose verdicts. A reviewer that returns "looks good" produced nothing.
- **A verification wave only helps if it differs** — a different prompt, evidence set, or role.
  Re-running the same prompt reproduces the same blind spot in parallel.
- **Do not fragment coherent work.** Schema changes, API contract changes, and tightly coupled
  refactors degrade when split into isolated contexts. Fan out over genuinely independent units.

## Escalate to a human

Stop and ask, regardless of remaining budget, when the run would: commit, push, tag, or publish;
mutate GitHub issues or the board; run a destructive or schema-changing migration; delete image or
score rows; export repo content to an external service; change a protected file; or disable the
evaluation it is being judged by. See [`.agent/SAFETY.md`](../../../.agent/SAFETY.md).

## Report when the run ends

State the objective, iterations used vs. budgeted, retained changes with their metric deltas,
reverted attempts worth knowing about, open questions, and why the run stopped. Feed durable
learnings to [`eval`](../eval/SKILL.md) → `/log-session`.

## Related

- [`karpathy-guidelines`](../karpathy-guidelines/SKILL.md) — per-change discipline inside each iteration
- [`/decompose`](../../commands/decompose.md) — building the independent units this contract governs
- [`validate-implementation`](../validate-implementation/SKILL.md) — per-AC verdicts when the metric is an AC matrix
- [`subagent-review`](../subagent-review/SKILL.md) — approval-gated external review fan-out
