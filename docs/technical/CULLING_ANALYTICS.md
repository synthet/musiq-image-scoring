# Culling and stack analytics

Technical reference for stack/culling statistics exposed via REST (`GET /api/analytics/culling`, session and per-stack variants).

**Implementation:** [`modules/culling_analytics/`](../../modules/culling_analytics/)  
**Diagnostic SQL:** [`scripts/sql/culling_analytics_diagnostics/`](../../scripts/sql/culling_analytics_diagnostics/)

## Decision layers

| Layer | Storage | Values |
|-------|---------|--------|
| Gallery flag | `images.pick_status` | `1` pick, `-1` reject, `0` neutral |
| Auto cull policy | `images.cull_decision` | `pick`, `reject`, `neutral`, … |
| Culling workspace | `culling_picks.decision` | `pick`, `reject`, `maybe`, NULL |

Library/folder analytics expose **two flag layers**:

| Response field | Source | When populated |
|----------------|--------|----------------|
| `flags.pick_count`, `reject_count`, `neutral_count` | `images.pick_status` | Manual culling UI, XMP import, or after Selection sync |
| `flags.auto_cull.*` | `images.cull_decision` | Automated Selection / two-level culling runs |
| `flags.by_cull_decision` | Raw `cull_decision` histogram | Always (includes `unset`) |
| `flags.auto_cull_stacks` | `cull_decision` per `stack_id` | Stack pick pattern + N=20 cap violations |
| `flags.auto_cull_substacks` | `sub_stacks` + `cull_decision` | Singleton-leaf %, M=3 violations, giant leaves |
| `hierarchy` | `stacks` + `sub_stacks` + `images` | Degenerate vs populated tiers, per-level decision averages, RCA samples |

**Note:** `SelectionService` writes `cull_decision` on every auto-cull run and (since 2026-06)
also syncs `pick_status` via `batch_update_cull_decisions`. Libraries upgraded before that
change need a one-time backfill: `python scripts/maintenance/backfill_pick_status_from_cull_decision.py`.

Session scope uses `culling_picks.decision` (`flags` on session endpoint).

## Confirmed schema

| Table / column | Use |
|----------------|-----|
| `stacks`, `images.stack_id` | Stack membership |
| `stack_cache` | Pre-aggregated min/max scores, `image_count` |
| `image_exif` | Exposure + GPS (no `metering_mode`, `white_balance`, `exposure_mode`) |
| `keywords_dim`, `image_keywords` | Keywords (`source`, `confidence`) |
| `image_embeddings` + `embedding_spaces` | 1280-d default `mobilenet_v2_imagenet_gap` |
| `culling_sessions`, `culling_picks` | Session workspace |

## API

| Method | Path | Scope |
|--------|------|-------|
| GET | `/api/analytics/culling` | Library or `folder_path` / `folder_id` |
| GET | `/api/analytics/culling/sessions/{session_id}` | Session picks |
| GET | `/api/analytics/stacks/{stack_id}` | Single stack drill-down |

Query params (library): `per_stack_limit`, `per_stack_offset` for paginated `scores.per_stack_summary`.

**Engine:** PostgreSQL only (`501` on Firebird).

## Config (`config.json`)

```json
"culling": {
  "analytics": {
    "visually_mixed_similarity": 0.85,
    "low_score_gap": 0.05
  }
}
```

## Composite metrics (heuristic)

| Metric | Range | Blocks auto-cull |
|--------|-------|------------------|
| `stack_consistency_score` | 0–1 | No |
| `review_priority_score` | 0–1 | No (warn/sort only) |
| `auto_pick_confidence` | 0–1 | No |

## Performance

- Library aggregates: live SQL on `images` / `stack_cache` (suitable for 100k+ images with indexes on `stack_id`, `folder_id`).
- Per-stack embeddings: pairwise cosine capped at 50 members; stacks truncated at 200 members.
- Phase 4 (optional): materialized folder snapshot — not in MVP.

## Edge cases

- Empty folder: zero counts, no error.
- Missing embeddings: `embeddings.coverage_pct` only; stack similarity omitted.
- `pick_status` vs `cull_decision` mismatch: listed in `warnings`.
- Degenerate hierarchy: `warnings` may include `singleton_root_stacks`, `single_leaf_stacks`.
- Stale `stack_cache`: per-stack score summary reads cache; use live `images` for flags.

## Hierarchy tiers (`hierarchy`)

| Tier | Condition | Degenerate? |
|------|-----------|-------------|
| `singleton_root` | Root stack `n = 1` | Yes — dissolve via `normalize_stack_hierarchy` |
| `single_leaf` | `n >= 2`, exactly one sub-stack covering all members | Yes — collapse sub-stack layer |
| `flat` | Multi-image stack, no `sub_stack_id` assignments | No |
| `populated_multi_leaf` | Two or more sub-stacks | No |
| Singleton leaves inside multi-leaf stacks | `image_count = 1` per sub-stack | Expected (~35% at threshold 0.06) |

**Tools:**

- Read-only audit: `python -m scripts.analyze_stack_hierarchy --json`
- SQL: [`06_stack_hierarchy_audit.sql`](../../scripts/sql/culling_analytics_diagnostics/06_stack_hierarchy_audit.sql)
- Maintenance: `python -m scripts.maintenance.normalize_degenerate_stacks` (dry-run default)

Per-stack drill-down (`GET /api/analytics/stacks/{id}`) adds `hierarchy_tier`, `decisions`,
`substacks`, `rca_hints`, and `embedding_coverage_pct`.

See diagnostic SQL files for copy-paste exploration queries.

## CLIP prompt-quality signal

`clip_quality_v0` is an **auxiliary** pick/reject signal (not a primary IQA model):
a 0–1 "good photo" probability from the persisted `clip_vit_b32_image` (512-d)
embedding compared against antonym text prompts (CLIP-IQA style). Benchmark:
[`reports/clip-culling/prompt-quality/`](../../reports/clip-culling/prompt-quality/)
— B/32 beat OpenCLIP/OpenAI-L14/BioCLIP, global pick/reject **AUC 0.89**, within-stack
keeper-vs-reject **concordance 0.986**.

- **Compute/storage:** [`modules/clip_quality.py`](../../modules/clip_quality.py) →
  `image_model_scores` (`model_name = clip_quality_v0`); surfaces in the API as
  `clip_quality_v0_score`. Backfill: `python scripts/maintenance/backfill_clip_quality.py`.
- **Phase-order note:** `clip_vit_b32_image` is normally produced in the *keywords*
  phase (after culling). When `culling.clip_quality.enabled`, culling JIT-generates it
  for stacked images via `ensure_embeddings_for_space` (same pattern as two-level
  level-2); the keywords phase then **reuses** that vector
  (`embeddings.reuse_clip_image_for_keywords`, default true) instead of re-encoding.
- **Use in culling:** blended into the within-stack `sort_key` at
  `culling.clip_quality.weight` (default 0.15), with an optional conservative
  `reject_below` floor. Default-off; `score_general` is left untouched. Config keys:
  [CONFIG.md](CONFIG.md#culling).
