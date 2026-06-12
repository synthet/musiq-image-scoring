# Cull decision distribution audit (2026-06)

Point-in-time audit of `images.cull_decision` / `cull_policy_version` at stack and sub-stack
levels vs documented thresholds. Diagnostic SQL:
[`05_cull_decision_distribution.sql`](../../scripts/sql/culling_analytics_diagnostics/05_cull_decision_distribution.sql).

**Config at audit time:** `culling.two_level.enabled=true`, M=3, N=20, `reject_non_picks=true`,
`level2.distance_threshold=0.06` (OpenCLIP L/14).

## Library summary

| Policy | Images | Stacked | Unstacked | pick | reject | neutral |
|--------|--------|---------|-----------|------|--------|---------|
| **1.0** (legacy) | 16,551 | 1,527 | 15,024 | 4,767 (29%) | 4,736 (29%) | 5,521 (33%) |
| **2.0** (active) | 46,418 | 44,172 | 2,246 | 22,511 (48%) | 18,157 (39%) | 5,750 (12%) |

Policy **2.0** overall percentages are **not** 33/33 — best-M + `reject_non_picks` dominates.

## Invariant checks (pass/fail)

| Check | Policy | Expected | Result |
|-------|--------|----------|--------|
| `floor(n×0.33)` pick/reject bands | 1.0 stacks n≥3 | picks = rejects = k | **PASS** (0 violations; no multi-image 1.0 stacks remain) |
| `sum(picks) ≤ 20` per root stack | 2.0 | N cap | **PASS** (0 over cap, 1 at cap) |
| `picks ≤ 3` per sub-stack | 2.0 | M cap | **PASS** (0 violations) |
| Singleton sub-stack → neutral | 2.0 | avg picks 0 | **PASS** (4,916 / 13,767 leaves = 35.7% singleton) |
| Threshold 0.06 split rate | 2.0 | ~35% singleton leaves | **PASS** (35.7% vs doc 35%) |
| `pick_status` reflects auto-cull | all | synced from `cull_decision` | **FIXED** — was all neutral; see backfill below |

## Policy 1.0 — 33/33 bands

**Code:** [`selection_policy.py`](../../modules/selection_policy.py) — `k = floor(n × 0.33)`.

| Group size | Expected |
|------------|----------|
| n=1 | neutral |
| n=2 | 1 pick, 1 neutral |
| n≥3 | k picks, k rejects, middle neutral |

**Live data:** All 1,527 policy-1.0 stacked images are **singleton stacks** (neutral). The
15,024 unstacked policy-1.0 images show ~29/29/33% library-wide because **unstacked images
per folder form one bucket** (`stack_id IS NULL` group in [`selection.py`](../../modules/selection.py)),
not per-image bands.

## Policy 2.0 — best-M / N-cap

**Code:** [`two_level_culling.py`](../../modules/two_level_culling.py), spec
[`two-level-culling.md`](../features/planned/embeddings/two-level-culling.md).

| Parameter | Config | Enforced |
|-----------|--------|----------|
| M (`picks_per_substack`) | 3 | yes (avg ~3.0 for sub-stacks size≥3) |
| N (`max_picks_per_stack`) | 20 | yes |
| `reject_non_picks` | true | ~0 neutrals in multi-image sub-stacks |
| Singleton leaf | neutral | yes |

**Sub-stack histogram (policy 2.0, selected):**

| Sub-stack size | Avg picks | Avg rejects | Notes |
|----------------|-----------|-------------|-------|
| 1 | 0.00 | 0.00 | all neutral |
| 2 | 1.99 | 0.01 | M capped to size |
| 7 | 3.00 | 4.00 | M=3 |
| 249+ | 3.00 | size−3 | failed sub-split → giant leaf |

## Outliers (informational, not invariant violations)

**Giant unsplit leaves** (`image_count > 50` in one sub-stack): stacks where level-2
clustering did not split (missing embeddings or threshold too loose). Examples: 249, 277
images with only 3 picks. Documented fallback; flag via `flags.auto_cull_substacks.giant_leaves_over_50`.

**Unstacked bucket under policy 2.0** (2,246 images): ~33/33/34% — uses **legacy 33/33 path**
because two-level only runs when `stack_id IS NOT NULL` and `len ≥ 2`.

## pick_status sync

Automated culling previously wrote `cull_decision` + XMP only. `batch_update_cull_decisions`
now also sets `pick_status`. One-time backfill for existing rows:

```bash
python -m scripts.backfill_pick_status_from_cull_decision --dry-run
python -m scripts.backfill_pick_status_from_cull_decision
```

## Analytics API

`GET /api/analytics/culling` → `flags.auto_cull`, `flags.auto_cull_stacks`,
`flags.auto_cull_substacks` report `cull_decision` distributions and invariant counters.
`flags.pick_count` / `reject_count` remain the manual `pick_status` layer.

## Conclusion

- **Policy 2.0 (active):** documented M/N/singleton/threshold targets are **followed** for stacked images.
- **Policy 1.0 (legacy):** residual rows comply where applied; no multi-image stacks remain.
- **Docs:** updated for floor rounding, analytics layers, two-level fallback, diagnostic SQL.

## Post-backfill verification (2026-06-11)

After OpenCLIP embedding backfill (62,969 / 62,969) and full sub-stacks refresh:

| Metric | Value |
|--------|-------|
| Root stacks processed | 10,795 |
| Sub-stacks written | 13,884 |
| Singleton leaves | 4,978 (35.8%) |
| Sub-stacks over M=3 | 0 |
| Giant leaves (size > 50) | 43 (informational) |
| Stacked policy 2.0 pick/reject/neutral | 21,871 / 17,324 / 4,977 |
| `pick_status` vs `cull_decision` disagree | 0 |
| OpenCLIP coverage | 100% |

Log: [`reports/clip-culling/backfill_sub_stacks_20260611.log`](../../reports/clip-culling/backfill_sub_stacks_20260611.log).
