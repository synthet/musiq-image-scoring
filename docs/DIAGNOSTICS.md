# Diagnostics

Use this page to inspect a local backend without guessing at config, database state, logs, or runner health.

## Project Doctor

From the repository root, prefer WSL with the same virtual environment as the Web UI:

```bash
source ~/.venvs/tf/bin/activate
python scripts/doctor.py
python scripts/doctor.py --no-gpu
python scripts/doctor.py --json
```

The doctor reports `PASS`, `WARN`, and `FAIL` checks and exits non-zero only on `FAIL`.

Checks include:

- `config.json` and `environment.json` structural sanity.
- Database initialization/connectivity.
- Simple query ping.
- PostgreSQL `vector` extension / pgvector availability.
- Optional CUDA/GPU probe unless `--no-gpu` is used.

Implementation: [scripts/doctor.py](../scripts/doctor.py), [modules/doctor_cli.py](../modules/doctor_cli.py).

## Watch A Run

With the Web UI running, poll a job/run:

```bash
source ~/.venvs/tf/bin/activate
python scripts/watch_run_http.py 2365
python scripts/watch_run_http.py 2365 --interval 5 --verbose
python scripts/watch_run_http.py 2365 --once
python scripts/watch_run_http.py 2365 --verbose --wsl-gateway
```

Use `--wsl-gateway` when Python runs in WSL but FastAPI is listening on Windows. Use `--base-url` when the server is not on the default host/port.

Implementation: [scripts/watch_run_http.py](../scripts/watch_run_http.py).

## Redacted Debug Bundle

Generate a support bundle:

```bash
source ~/.venvs/tf/bin/activate
python scripts/export_debug_bundle.py
python scripts/export_debug_bundle.py --output /tmp/my-bundle.zip
```

The bundle uses redaction helpers in [modules/redact_sensitive.py](../modules/redact_sensitive.py) and [modules/doctor_cli.py](../modules/doctor_cli.py). `secrets.json` is excluded. Review the zip before sharing; do not commit debug bundles without explicit review.

## Logs

Typical local files:

- `webui.log` - server, request, runner, and startup logs.
- `debug.log` - structured pipeline/debug events when configured.

MCP log tools include `read_debug_log`, `get_server_log_tail`, and `search_logs`.

## MCP Diagnostics

When an MCP client is attached, use **compact search + dispatch** on **`is-be-mcp`**:

1. **`search("…")`** → pick `action_id` from results
2. **`dispatch("diagnostics.get_error_summary", {})`**, **`dispatch("diagnostics.run_doctor", {"no_gpu": true})`**, etc.

Examples:

```text
search("why did scoring fail")
dispatch("diagnostics.get_error_summary", {})

search("run doctor without gpu")
dispatch("diagnostics.run_doctor", {"no_gpu": true})
```

Legacy: domain servers (`is-be-diag`, `is-be-jobs`) and **`is-be-router`** `be_find` remain for compatibility. See [MCP_SEARCH_DISPATCH.md](technical/MCP_SEARCH_DISPATCH.md).

For a diagnostics-only profile, keep **`is-be-maint`** disabled and avoid write/code tools on SSE (`execute_code`, …).

Full catalog: [AGENTS.md](../AGENTS.md) and [.agent/mcp_tools_reference.md](../.agent/mcp_tools_reference.md).

## Images: phase icon vs stored data

If `/ui/images` shows keywords (or other phases) as incomplete after **completed** auto-drive runs:

1. Open the image inspector **Phase audit log** (or `GET /api/images/{id}/auditlog`).
2. Look for `done` → `not_started` or `done` → `failed` on `keywords` shortly after a run — usually `_heal_stale_phase_flags` or caption-only tagging (no normalized `image_keywords` rows).
3. Use list filters `phase_status=keywords:not_started`, `data_gap=keywords`, or `unscored_only=true` on `GET /api/images`.
4. Stop the durable drive loop while fixing data: `POST /api/runs/drive/stop`.

## Related

- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- [TESTING.md](TESTING.md)
- [.agent/INFRA_QUICKSTART.md](../.agent/INFRA_QUICKSTART.md)
