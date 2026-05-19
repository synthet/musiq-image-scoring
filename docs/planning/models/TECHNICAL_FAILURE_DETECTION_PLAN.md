# Technical failure detection

MVP (issue #143): classical metrics during the **scoring** phase — no new pipeline phase.

## Config (`technical_failures`)

| Key | Default | Purpose |
|-----|---------|---------|
| `enabled` | `false` | Run detector after `run_all_models()` |
| `use_classical_metrics` | `true` | Laplacian blur + histogram exposure |
| `use_clip_iqa` / `use_pyiqa` | `false` | Reserved (#144) |
| `fail_on_detector_error` | `false` | Fail scoring when detector throws |
| `version` | `1.0.0` | Payload version string |

## API shape

`technical_failure_detection`: `version`, `technical_failure_score` (0–100), `primary_reject_reason`, nested `technical_failures` metrics.

Tie-break for `primary_reject_reason`: blur → overexposed → underexposed → highlight_clipping → shadow_crushing (threshold 0.3).

## Storage

PostgreSQL `image_technical_failures` (PK `image_id`). Firebird dual-write via legacy init when engine is Firebird.
