# Stack hierarchy audit (2026-06)

Point-in-time audit of root stack / sub-stack hierarchy shape, pick/reject/neutral
rollups, and degenerate vs populated tiers. Generated from
`python -m scripts.analyze_stack_hierarchy --json` on the live library.

Diagnostic SQL: [`06_stack_hierarchy_audit.sql`](../../scripts/sql/culling_analytics_diagnostics/06_stack_hierarchy_audit.sql).

## Library summary (62,967 images)

| Decision layer | pick | reject | neutral |
|----------------|------|--------|---------|
| `images.cull_decision` (all images) | 27,369 (43.5%) | 22,792 (36.2%) | 12,806 (20.3%) |
| Avg per root stack (stacked only) | 2.03 | 1.61 | 0.60 |
| Avg per sub-stack | 1.57 | 1.25 | 0.36 |

`pick_status` vs `cull_decision` disagree: **0**.

## Hierarchy tiers

| Tier | Stacks | Images | Degenerate? |
|------|--------|--------|-------------|
| **Singleton root** (`n = 1`) | 1,533 | 1,533 | Yes |
| **Single-leaf** (1 sub-stack = whole stack, `n >= 2`) | 6,006 | 22,532 | Yes |
| **Populated multi-leaf** (`leaf_count >= 2`) | 3,242 | 21,632 | No |
| Flat (no sub-stacks) | 0 | 0 | — |

**Total root stacks:** 10,781 (1,533 + 6,006 + 3,242).

## Sub-stack leaves

| Metric | Value |
|--------|-------|
| Total sub-stacks | 13,888 |
| Singleton leaves (size = 1) | 4,980 (35.9%) |
| Expected singleton leaves (inside multi-leaf stacks only) | 4,975 |
| Giant leaves (size > 50) | 43 (informational) |
| Sub-stacks over M=3 picks | 0 |

The ~36% singleton-leaf rate matches the documented threshold-0.06 target
([`CULL_DISTRIBUTION_AUDIT_2026-06.md`](CULL_DISTRIBUTION_AUDIT_2026-06.md)).
These are **not** degenerate — only single-leaf **stacks** (one sub-stack covering
the entire root stack) are redundant hierarchy.

## RCA — how degenerate tiers appeared

### Singleton root stacks (1,533)

Clustering never creates stacks with fewer than two images
([`clustering.py`](../../modules/clustering.py)). Likely causes:

- Manual **remove from stack** leaving one member (before `normalize_stack_hierarchy`)
- Partial **prune_missing_files** removing stack mates
- Legacy data from earlier pipeline versions

**Remediation:** `db.normalize_stack_hierarchy(stack_id)` dissolves these (ungroup).
Bulk: `python -m scripts.maintenance.normalize_degenerate_stacks --only singleton_root --live`.

### Single-leaf stacks (6,006)

Root stack has `n >= 2` but OpenCLIP sub-clustering produced **one leaf** covering all
images. Common causes:

- **Embedding fallback** when level-2 vectors were missing at backfill time (whole stack
  collapsed to one bucket in `compute_sub_clusters`)
- **Stack size = 2** with high visual similarity (no split at threshold 0.06)
- Threshold too loose for the stack's visual diversity

With `skip_single_leaf_persist=true` (new default), future Selection/backfill runs will
assign decisions at stack level and **not** persist a redundant `sub_stacks` row.

**Remediation:** `normalize_stack_hierarchy` collapses the sub-stack layer in place.
Bulk: `python -m scripts.maintenance.normalize_degenerate_stacks --only single_leaf --live`.

## Populated stacks (3,242 multi-leaf)

These are the stacks where two-level hierarchy adds value: multiple visual groups per
burst/root stack, best-M picks per leaf, N=20 cap at root level.

Average ~6.7 images per populated stack; 4,975 singleton leaves inside these stacks are
normal micro-splits at threshold 0.06.

## Tools added

| Tool | Purpose |
|------|---------|
| `scripts/analyze_stack_hierarchy.py` | Read-only JSON/human report |
| `GET /api/analytics/culling` → `hierarchy` | Library/folder tier counts + decision rollups |
| `GET /api/analytics/stacks/{id}` | Per-stack `hierarchy_tier`, `substacks`, `rca_hints` |
| `db.normalize_stack_hierarchy()` | Dissolve / collapse / prune after membership changes |
| `scripts/maintenance/normalize_degenerate_stacks.py` | Bulk repair (dry-run default) |

Baseline JSON: [`reports/stack_hierarchy_baseline.json`](../../reports/stack_hierarchy_baseline.json).

## Post-normalization verification (2026-06-13)

After `python -m scripts.maintenance.normalize_degenerate_stacks --live` (7,539 stacks):

| Action | Count |
|--------|-------|
| Dissolved singleton roots | 1,533 |
| Collapsed single-leaf (1:1 sub-stack layer removed) | 6,006 |

### Hierarchy tiers (after)

| Tier | Stacks | Change from baseline |
|------|--------|----------------------|
| Singleton root | **0** | −1,533 |
| Single-leaf (1:1) | **0** | −6,006 |
| Flat (multi-image, no sub-stacks) | **6,006** | +6,006 |
| Populated multi-leaf | **3,242** | unchanged |

**Degenerate stack IDs:** 0.

### Sub-stack leaves (after)

| Metric | Before | After |
|--------|--------|-------|
| Total sub-stacks | 13,888 | **7,877** |
| Expected singleton leaves (multi-leaf only) | 4,975 | **4,975** |
| Singleton leaf % (all sub-stacks) | 35.9% | 63.2%* |

\* The headline singleton-leaf % rose because 6,006 whole-stack single-leaf rows were
removed from the denominator. The count of expected singleton leaves inside multi-leaf
stacks is unchanged — still normal at threshold 0.06.

### Decisions (unchanged)

| pick | reject | neutral |
|------|--------|---------|
| 27,369 | 22,792 | 12,806 |

Normalization repaired hierarchy shape only; `cull_decision` / `pick_status` were not
rewritten.

After JSON: [`reports/stack_hierarchy_after.json`](../../reports/stack_hierarchy_after.json).

**Ongoing:** `skip_single_leaf_persist` and `remove_images_from_stack` →
`normalize_stack_hierarchy` prevent re-accumulation of degenerate tiers on new runs and
manual edits.
