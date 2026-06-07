# MCP search + dispatch contract

**Authority:** Action registry [`mcp/action_registry.json`](../../mcp/action_registry.json), overlay [`mcp/actions/overlay.yaml`](../../mcp/actions/overlay.yaml). Planning: [`docs/planning/mcp-search-dispatch.md`](../planning/mcp-search-dispatch.md).

## Preferred agent entry point

| Server | Tools | Use |
|--------|-------|-----|
| **`is-be-mcp`** | **`search`**, **`dispatch`** | **New agents** — compact, stable surface |
| **`is-be-router`** | `search`, `dispatch`, deprecated `be_find`, `be_card`, `be_domains` | Legacy agents |
| **`is-be-diag`**, **`is-be-jobs`**, **`is-be-data`** | Legacy per-operation tools | Debug / compatibility only |

## Workflow

```text
1. search("why did scoring fail")     # on is-be-mcp
2. dispatch("diagnostics.get_error_summary", {})
3. dispatch("jobs.get_failed_images", {"limit": 20})
```

## `search`

```python
search(
    query: str,
    limit: int = 10,
    category: str | None = None,
    side_effect_level: str | None = None,
    read_only_only: bool = False,
    pipeline_area: str | None = None,
    include_schemas: bool = False,
    include_docs: bool = False,
    include_elevated: bool = False,
) -> dict
```

- Searches **action registry** only; never executes side effects.
- Returns `results[]` with `action_id`, `confidence`, `dispatch_hint`, `required_args`, `optional_args`.
- Sets `low_confidence: true` when top match is weak.

## `dispatch`

```python
dispatch(
    action_id: str,
    arguments: dict | None = None,
    dry_run: bool = False,
    confirmed: bool = False,
    request_id: str | None = None,
    allow_deprecated: bool = False,
    expected_version: int | None = None,
) -> dict
```

### Success envelope

```json
{
  "action_id": "diagnostics.get_error_summary",
  "action_version": 1,
  "request_id": "…",
  "status": "success",
  "side_effect_level": "read_only",
  "dry_run": false,
  "summary": "…",
  "data": {},
  "warnings": [],
  "errors": [],
  "artifacts": [],
  "logs_ref": null,
  "canonical_docs": ["docs/DIAGNOSTICS.md"]
}
```

### Error envelope

`status: "error"`, `code` (`unknown_action`, `validation_error`, `policy_rejected`, `confirmation_required`, `unsupported_dry_run`, …), `message`, `request_id`.

## Dispatchable actions

### Read-only (PR1)

| action_id | Example arguments |
|-----------|-----------------|
| `diagnostics.run_doctor` | `{"no_gpu": true}` |
| `diagnostics.get_error_summary` | `{}` |
| `diagnostics.check_database_health` | `{}` |
| `diagnostics.validate_config` | `{}` |
| `diagnostics.get_database_engine_info` | `{}` |
| `diagnostics.verify_environment` | `{}` |
| `diagnostics.get_model_status` | `{}` |
| `logs.read_debug_log` | `{"lines": 100}` |
| `logs.get_server_log_tail` | `{"sources": "all", "lines": 100}` |
| `logs.search_logs` | `{"pattern": "error\|failed"}` |
| `config.get_config` | `{}` |
| `jobs.get_failed_images` | `{"limit": 20}` |
| `jobs.get_run_diagnostics` | `{"run_id": 123}` |
| `data.get_embedding_stats` | `{}` |

### Side-effecting (confirmation required)

| action_id | Example arguments | Notes |
|-----------|-------------------|-------|
| `support.export_debug_bundle` | `{"confirmed": true}` via dispatch | Writes redacted zip; `output_path` optional (`.zip` only); returns metadata + `review_reminder` |

## Legacy tool mapping

| action_id | Legacy MCP tool | Domain server |
|-----------|-----------------|---------------|
| `diagnostics.get_error_summary` | `get_error_summary` | `is-be-diag` |
| `jobs.get_run_diagnostics` | `get_run_diagnostics` | `is-be-jobs` |
| `data.get_embedding_stats` | `get_embedding_stats` | `is-be-data` |

## Common agent workflows

Attach **`is-be-mcp`**, then **`search`** → **`dispatch`**. If `low_confidence` is true, refine the query or use a legacy domain server.

### Scoring failure triage

```text
search("why did scoring fail")
dispatch("diagnostics.get_error_summary", {})
dispatch("jobs.get_failed_images", {"limit": 20})
dispatch("logs.search_logs", {"pattern": "error|failed"})
```

### System health

```text
dispatch("diagnostics.check_database_health", {})
dispatch("diagnostics.validate_config", {})
```

### Doctor (no GPU)

```text
dispatch("diagnostics.run_doctor", {"no_gpu": true})
```

### Export debug bundle (writes_files)

```text
search("export debug bundle")
dispatch("support.export_debug_bundle", {}, confirmed=True)
# optional: {"output_path": "exports/debug-bundles/my-bundle.zip"}
```

Review the zip before sharing. `secrets.json` is never included.

### Still unsupported via compact dispatch

`execute_sql`, `execute_code`, maintenance writes/jobs, and other side-effecting actions unless listed above and in `ALLOWED_SIDE_EFFECT_ACTIONS`.

## Vocabulary (do not use)

- `imgscore-py-*`, `image-scoring-backend-*`, `is-ga-*`
- Calling 50+ legacy tools from **new** agent configs (use `is-be-mcp` instead)

## Gallery

Backend compact MCP is authoritative for diagnostics/pipeline. Gallery uses **`is-ui-*`** (`ui_find`, …) until gallery `search`/`dispatch` mirrors land (later phase).
