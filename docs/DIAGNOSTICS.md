# Diagnostics

This page lists **how to inspect** a local image-scoring-backend install without starting the full Web UI.

## Project doctor (CLI)

From the repository root, prefer **WSL** with the same venv as the Web UI (`~/.venvs/tf` per [DEVELOPMENT.md](DEVELOPMENT.md)):

```bash
source ~/.venvs/tf/bin/activate
python scripts/doctor.py
python scripts/doctor.py --no-gpu
python scripts/doctor.py --json
```

- **PASS / WARN / FAIL** summary is printed at the end.
- Exit code **1** only on **FAIL** (so CI can gate on `python scripts/doctor.py`).
- Checks: structural `config.json` / `environment.json` validation, DB init, simple query ping, **pgvector** extension on PostgreSQL, optional **CUDA** probe (unless `--no-gpu`).

Implementation: [`scripts/doctor.py`](../scripts/doctor.py), [`modules/doctor_cli.py`](../modules/doctor_cli.py).

## Redacted debug bundle

For support or bug reports, generate a **zip** with redacted config and doctor output (no secrets):

```bash
source ~/.venvs/tf/bin/activate
python scripts/export_debug_bundle.py
python scripts/export_debug_bundle.py --output /tmp/my-bundle.zip
```

Redaction uses **`redact_json_obj`** — implemented in [`modules/redact_sensitive.py`](../modules/redact_sensitive.py) and re-exported from [`modules/doctor_cli.py`](../modules/doctor_cli.py) for doctor/tests/bundles (key substrings such as `password`, `secret`, `token`, `api_key`, …). `secrets.json` is never included. Review the zip before sharing.

## MCP tools (when the MCP server or Web UI is running)

When Cursor (or another MCP client) is attached to **image-scoring**, use tools such as `validate_config`, `verify_environment`, `get_database_engine_info`, `check_database_health`, and log tails — see [AGENTS.md](../AGENTS.md) and [.agent/mcp_tools_reference.md](../.agent/mcp_tools_reference.md).

### Read-only MCP profile (`imgscore-py-sse` / `imgscore-el-sse`)

The SSE server runs inside the live Web UI process. To reduce accidental writes or arbitrary code execution, Cursor supports **`disabledTools`** on each MCP server entry. For a diagnostics-only profile, disable at least:

- `execute_code` (requires `ENABLE_MCP_EXECUTE_CODE=1`; still high risk on shared hosts)
- `set_config_value`
- `run_processing_job`
- `process_newly_imported_folders`
- `rebase_file_paths`
- `prune_missing_files`
- `set_image_metadata`
- `propagate_tags`
- `manage_runners` (can stop in-process runners)

Keep read tools such as `get_error_summary`, `get_failed_images`, `get_db_schema`, `execute_sql`, `search_logs`, `get_job_details`, and `export_debug_bundle` enabled for triage. Adjust the list to your workflow (e.g. allow `run_processing_job` only when you intentionally start runs from the agent).

## Logs

Typical locations (see also `get_server_log_tail`, `read_debug_log`, and `search_logs` in MCP):

- `webui.log` — server / request issues
- `debug.log` — structured JSON lines from pipeline components (path may depend on `system.log_dir` in config)

## Related

- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — where to look when something fails
- [TESTING.md](TESTING.md) — running tests after infra changes
