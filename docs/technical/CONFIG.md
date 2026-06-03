# Configuration (`config.json`)

Authority for runtime settings in **image-scoring-backend**. Implementation: [`modules/config.py`](../../modules/config.py).

## Files

| File | Git | Role |
|------|-----|------|
| `config.json` | Usually local / not committed | Base settings; **writes** from API, Gradio, MCP `set_config_value` |
| `environment.json` | Gitignored (see `environment.example.json`) | Machine overrides; **deep-merged on read** over `config.json` |
| `secrets.json` | Gitignored | API credentials per service (`get_secret()`); never merge into `load_config()` |
| `config.example.json` | Committed | Template for new installs |

**Read path:** `load_config()` = `config.json` merged with `environment.json` (override wins).

**Write path:** `save_config_value` / `save_config_section` update **`config.json` only** (not `environment.json`).

## Access API

```python
from modules.config import load_config, get_config_value, get_config_section

get_config_value("scoring.force_rescore_default", default=False)
get_config_section("clustering")
```

Dot notation walks nested dicts. After config changes that affect scoring composites, call `modules.score_normalization.reload_config()` (separate in-process cache).

## REST endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/config` | **Public flags** for React (`ConfigResponse`: `enable_culling`, `embedding_map_enabled`, `db_explorer_enabled`, `scoring_models`) |
| GET | `/api/config/full` | Full merged config (Settings / integrations); sensitive fields should be redacted by callers |
| POST | `/api/config/{section}` | Replace one section in `config.json` (whitelist: `scoring`, `processing`, `culling`, `ui`, `tagging`) |

Gradio Settings tab saves via `save_config_section` with **merge** into existing sections (preserves `scoring.models`, `fusion`, etc.).

## Secrets vs config

| Secret | Location |
|--------|----------|
| REST `X-API-Key` | `API_KEY` env, or `api.key` in config (prefer env) |
| DB write SQL gate | `database.query_token` in config — prefer moving to env/secrets for production |
| Cursor / Claude / geocoding keys | `secrets.json` via `get_secret(service_name)` |

Do not commit real passwords or tokens in `config.json`.

## Cross-repo (gallery)

**image-scoring-gallery** reads the same sibling `config.json` when co-located. Postgres connection:

- Backend: `database.postgres.dbname`
- Gallery normalizer: accepts `postgres.database` as alias → maps to `database` field internally

Use **`dbname`** in backend docs and `config.example.json`.

## Sections (primary readers)

### `scoring`

Quality analysis defaults, model membership, fusion weights, per-model options.

| Key | Reader | Default if omitted |
|-----|--------|-------------------|
| `force_rescore_default` | UI / runners | `false` |
| `default_sort_by`, `default_sort_order` | UI | `score_general`, `desc` |
| `fusion` | `score_normalization.get_composite_weights()` | See `DEFAULT_COMPOSITE_WEIGHTS` in code |
| `models` | `engines/registry.py`, `GET /api/config` | All models enabled in code paths |
| `arniqa`, `qpt_v2`, `cursor`, `claude` | Respective scorer modules | Module defaults |

### `percentile_anchors`

Per-model `p02` / `p98` for composite rescaling (`score_normalization`).

### `technical_failures` (top-level)

Blur/focus detection during scoring (`modules/pipeline.py`). Subkeys: `enabled`, `use_classical_metrics`, `use_clip_iqa`, `use_pyiqa`, `fail_on_detector_error`, `version`.

### `processing`

Queue sizes and job behavior.

| Key | Reader |
|-----|--------|
| `prep_queue_size`, `scoring_queue_size`, `result_queue_size` | `engine.py`, clustering |
| `clustering_batch_size` | `clustering.py` |
| `strict_job_completion_verify` | `db_legacy.py` |
| `post_run_data_quality_audit`, `post_run_audit_fail_job_on_issues` | Post-run audit |
| `job_action_log_retention_days` | `scripts/maintenance/cleanup_stale_logs.py` |

### `clustering`

Similarity clustering (culling phase stacks). **`default_threshold`** and **`default_time_gap`** are the canonical tuning knobs for `ClusteringEngine.cluster_images()`.

| Key | Reader |
|-----|--------|
| `stack_representative_strategy` | `clustering.py` (`score` \| `centroid` \| `balanced`) |
| `best_image_strategy` | **Deprecated** alias for `stack_representative_strategy` |
| `best_image_alpha` | Balanced representative blend |
| `heal_folder_cohesion_candidates`, `heal_cohesion_*` | `workflow_healing.py` |
| `force_rescan_default` | Clustering runner |

### `culling`

Session-based culling UI and selection pipeline. Duplicates **`default_threshold`** / **`default_time_gap`** for the legacy culling session import path (`modules/culling.py`). Gradio Settings writes the same values to **both** `clustering` and `culling` when saving stack tuning.

| Key | Reader |
|-----|--------|
| `enabled` | `GET /api/config` → `enable_culling` (React feature flag) |
| `sub_cluster_distance_threshold` | `culling.py`, `selection.py` |
| `two_level` | `selection.py`, two-level culling |
| `analytics.*` | `culling_analytics/composite.py` |

### `tagging`

Keywords / captions / CLIP model id.

### `ui`

Gallery page size, export format, `last_selected_folder` (runtime).

### `database`

| Key | Reader |
|-----|--------|
| `engine` | `get_database_engine()`: `postgres`, `firebird` (legacy), `api` |
| `postgres.*` | `db_postgres.py` (`host`, `port`, `dbname`, `user`, `password`) |
| `write_legacy_keywords_column`, `write_legacy_image_embedding_column` | Dual-write toggles |
| `enable_api_db_query`, `api_db_query_max_rows`, `query_token` | `api_db.py` |
| `db_explorer_enabled` | React DB explorer |
| `audit_log_enabled`, `audit_log_tables` | `modules/audit.py` |
| `strict_phase_transitions`, `stale_running_threshold_seconds` | Phase / job hygiene |

### `embeddings`

Persistence flags, `culling_spaces` for backfill scripts, `model_versions` map.

### `embedding_map`

UMAP/projection UI (`projections.py`). Default `max_points`: **15000**.

### `system`

| Key | Reader |
|-----|--------|
| `allowed_paths` | `webui.py`, `security._validate_file_path` (with legacy top-level fallback) |
| `log_dir` | `utils.py`, log views |
| `log_max_bytes`, `log_backup_count` | Log rotation when configured |

### `raw_conversion`

RAW/NEF preview pipeline (`preprocess_image`).

### `paths`

WSL/Windows host project roots for thumbnail path rebasing.

### `indexing` (often in `environment.json`)

| Key | Reader |
|-----|--------|
| `hash_mode` | `image_identity_hash.py`, indexing runner |
| `nikon_nef_only`, `excluded_paths` | `indexing_policy.py` |
| `photos_prune_*` | `photos_top_segment_prune.py` |

### `geocoding` (optional)

`enabled`, `provider`, `nominatim_base_url`, `user_agent`, `min_interval_seconds`, `http_timeout_seconds`.

### `pipeline`

`auto_resume_interrupted` — orchestrator resume policy.

### `auto_drive`

| Key | Default | Notes |
|-----|---------|--------|
| `server_loop_enabled` | `true` | Runs the server-side drive loop (`drive_tick` on idle). |
| `prioritize_new_folders` | `true` | When true, folders with `folders.created_at` within `new_folder_days` sort before older backlog (even across pipeline phases). |
| `new_folder_days` | `7` | Window for “newly imported” folder boost; aligned with MCP `get_newly_imported_folders`. |

### Top-level misc

| Key | Notes |
|-----|--------|
| `debug` | Diagnostics summary only |
| `webui_host`, `webui_port` | Often in `environment.json` |
| `export_templates` | Saved export presets (runtime) |
| `rating_thresholds`, `label_thresholds` | Optional; code defaults in `score_normalization` |

## Deprecated / legacy keys

| Key | Replacement / note |
|-----|-------------------|
| `scoring_input_path`, `tagging_input_path`, `stacks_input_path`, `culling_input_path`, `selection_input_path` | **Deprecated** — Gradio-era defaults; runs use API `scope_paths`. Still validated as path warnings only. |
| `composite_weights` (top-level) | Use `scoring.fusion` |
| `clustering.best_image_strategy` | Use `stack_representative_strategy` |
| Top-level `allowed_paths` | Use `system.allowed_paths` (legacy fallback in security helper) |

## Writable surfaces

| Surface | Sections |
|---------|----------|
| `POST /api/config/{section}` | `scoring`, `processing`, `culling`, `ui`, `tagging` only |
| Gradio Settings | Same sections + `clustering` (merged save) |
| MCP `set_config_value` | Any dot path → `config.json` |
| Manual edit | Any key |

For `clustering`, `database`, `embeddings`, `system`: edit `config.json` or use MCP unless API whitelist is extended.

## Validation

`modules.config.validate_config()` — structural checks (queues, postgres fields when `engine=postgres`, indexing types). Does not validate fusion weights or culling thresholds. MCP `validate_config` adds optional DB ping.

## Related docs

- [WEIGHTED_SCORING_STRATEGY.md](WEIGHTED_SCORING_STRATEGY.md) — `scoring.fusion` / `scoring.models`
- [EMBEDDINGS.md](EMBEDDINGS.md) — embedding spaces and persistence
- [features/implemented/04-clustering-culling-stacks.md](../features/implemented/04-clustering-culling-stacks.md) — clustering tuning
- [environment.example.json](../../environment.example.json) — per-machine paths and indexing
