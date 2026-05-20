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

Library/folder analytics use **`pick_status`** unless noted as session scope.

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
- Stale `stack_cache`: per-stack score summary reads cache; use live `images` for flags.

See diagnostic SQL files for copy-paste exploration queries.
