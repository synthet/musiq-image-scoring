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

When an MCP client is attached, use read-oriented tools before mutating anything:

- `validate_config`
- `verify_environment`
- `get_database_engine_info`
- `check_database_health`
- `get_error_summary`
- `get_failed_images`
- `get_recent_jobs`
- `get_job_details`
- `get_job_phases`
- `get_run_diagnostics`
- `get_stale_running_phase_status`
- `search_logs`

For a diagnostics-only MCP profile, disable write/code tools such as `execute_code`, `set_config_value`, `run_processing_job`, `process_newly_imported_folders`, `rebase_file_paths`, `prune_missing_files`, `set_image_metadata`, `propagate_tags`, and `manage_runners`.

Full MCP catalog: [AGENTS.md](../AGENTS.md) and [.agent/mcp_tools_reference.md](../.agent/mcp_tools_reference.md).

## Related

- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- [TESTING.md](TESTING.md)
- [.agent/INFRA_QUICKSTART.md](../.agent/INFRA_QUICKSTART.md)
