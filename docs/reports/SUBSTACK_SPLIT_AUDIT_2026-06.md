---
type: Report
title: Sub-stack split and agent-cull batching audit
description: Live library metrics, threshold sweep, and config changes (2026-06)
timestamp: 2026-06-30
okf_version: 0.1
---

# Sub-stack split + agent-cull batching audit (2026-06)

Point-in-time audit before retuning `culling.two_level.level2.distance_threshold` and
enabling batched agentic cull review. Generated from:

- `python -m scripts.analyze_stack_hierarchy --json`
- `python -m scripts.study.substack_split_audit`
- `python -m scripts.study.substack_threshold_sweep --limit 150 --min-stack-size 10`

## Library summary (~64,880 images)

| Metric | Value |
|--------|-------|
| Root stacks | 9,966 |
| **Flat** (no `sub_stack_id`) | **5,370 stacks / 21,972 images** |
| **Single-leaf** (1 sub-stack = whole stack) | **2,935 stacks / 15,019 images** |
| Populated multi-leaf | 1,655 stacks / 16,238 images |
| Total sub-stacks | 7,242 |
| Giant leaves (size > 50) | 41 |
| OpenCLIP L/14 coverage (stacked images) | **99.72%** (53,090 / 53,238) |

### Root cause notes

1. **Flat stacks (5,370)** — images have `stack_id` but no `sub_stack_id`. These behave as one
   agent-cull unit per root stack. Re-run Selection with `culling.two_level.enabled: true` or
   `python -m scripts.maintenance.backfill_sub_stacks` to populate sub-stacks.
2. **Single-leaf stacks (2,935)** — level-2 clustering at threshold **0.06** did not split;
   common causes: missing OpenCLIP embeddings (fallback bucket in `compute_sub_clusters`),
   genuinely similar bursts, or threshold too loose.
3. **Agent skip** — with `max_group_size: 200` and `review_batch_size: 10`, post-change audit
   shows **0** `group_too_large` / safety-ceiling skips in a full-library scan; oversized leaves
   are reviewed in batches instead.

## Threshold sweep (OpenCLIP L/14, stacks n≥10, sample 150)

| Threshold | Single-leaf stacks (sample) | Giant leaves | Leaves > batch (10) | % leaves ≤ 10 |
|-----------|----------------------------|--------------|---------------------|---------------|
| 0.02 | 0 | 3 | 47 | 99.2% |
| 0.03 | 2 | 9 | 133 | 96.3% |
| **0.04** | **10** | **16** | **190** | **90.9%** |
| 0.06 (prior) | 37 | 45 | 219 | 73.1% |
| 0.08 | 70 | 53 | 187 | 54.6% |

**Chosen threshold: 0.04** — balances sweep metrics vs over-splitting near-duplicates.
Sweep minimum single-leaf was **0.02**; we avoid that extreme default because it can
fragment true burst sequences. Remaining leaves >10 are handled by agent batching.

## Config changes applied

| Key | Before | After |
|-----|--------|-------|
| `culling.two_level.level2.distance_threshold` | 0.06 | **0.04** |
| `culling.two_level.min_stack_size_for_substack` | (dead) | **3** (wired) |
| `culling.two_level.skip_single_leaf_persist` | (dead) | **true** (wired) |
| `culling.agent_review.max_group_size` | 9 | **200** (safety ceiling) |
| `culling.agent_review.review_batch_size` | (new) | **10** |

## Follow-up (operator)

1. OpenCLIP coverage is **99.72%** — no embedding backfill required before sub-stack retune.
2. ~~Re-run sub-stacking on the library~~ — **done** 2026-07-01 (see below).
3. ~~Re-run audit after live backfill~~ — **done** 2026-07-01 (see below).
4. Agent cull dry-run on giant leaves (`dry_run_default: true`).

## Post-backfill (2026-07-01, threshold 0.04)

Full library run: `python -u -m scripts.maintenance.backfill_sub_stacks --resume
--checkpoint reports/clip-culling/backfill_sub_stacks_0.04.checkpoint.json` (WSL,
9,982 stacks, ~10 min). Checkpoint: pick=24,801 reject=17,356 neutral=11,081.

| Metric | Before (0.06) | After (0.04 backfill) |
|--------|---------------|------------------------|
| Flat stacks (no `sub_stack_id`) | 5,370 | **5,209** |
| Single-leaf persisted stacks | 2,935 | **0** (`skip_single_leaf_persist`) |
| Populated multi-leaf | 1,655 | **4,752** |
| Giant leaves (size > 50) | 41 | **12** |
| Agent `group_too_large` skips | — | **0** |

Leaf histogram: 1-image leaves 12,652; 2–3: 4,922; 4–9: 1,527; 10–20: 264; 21–50: 85; 51+: 12.

SQL spot-checks: 5,209 multi-image stacks still have no `sub_stacks` row (expected when
level-2 collapses to one leaf and `skip_single_leaf_persist: true`); 14,256 images with
`stack_id` but `sub_stack_id IS NULL`. Agent batching covers oversized leaves.

Log: [`reports/clip-culling/backfill_sub_stacks_0.04.log`](../../reports/clip-culling/backfill_sub_stacks_0.04.log)

## Related

- [`STACK_HIERARCHY_AUDIT_2026-06.md`](STACK_HIERARCHY_AUDIT_2026-06.md)
- [`CULL_DISTRIBUTION_AUDIT_2026-06.md`](CULL_DISTRIBUTION_AUDIT_2026-06.md)
- [`CULLING_MODEL_RECOMMENDATION_2026-05-29.md`](CULLING_MODEL_RECOMMENDATION_2026-05-29.md)
