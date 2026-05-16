# Troubleshooting

Hub page for first-response diagnostics. Follow links for detailed failure modes instead of duplicating API, schema, or runner internals here.

## First Steps

1. Activate the WebUI venv and run the doctor:

   ```bash
   source ~/.venvs/tf/bin/activate
   python scripts/doctor.py
   ```

2. If GPU setup is not relevant, rerun with `python scripts/doctor.py --no-gpu`.
3. If MCP is available, use **`validate_config`**, **`get_database_engine_info`**, **`check_database_health`**, and job/log read tools; see [AGENTS.md](../AGENTS.md) and [technical/MCP_DEBUGGING_TOOLS.md](technical/MCP_DEBUGGING_TOOLS.md).
4. Check recent logs before changing code.

## Logs

- `webui.log` - server startup, request, and WebUI errors.
- `debug.log` - structured pipeline events; location may depend on `system.log_dir`.
- MCP tools such as `get_server_log_tail`, `read_debug_log`, and `search_logs` can inspect logs when the server is reachable.

See [DIAGNOSTICS.md](DIAGNOSTICS.md) for doctor and debug-bundle commands.

## Common Failure Categories

- **Config or environment:** invalid `config.json`, missing venv packages, wrong API host/port, Windows/WSL path mismatch.
- **Database:** PostgreSQL unreachable, bad credentials, missing migrations, missing **pgvector**, stale `running` rows, schema drift.
- **Pipeline/jobs:** queued/running jobs stuck, runner unavailable, phase mismatch, invalid operation tokens.
- **GPU/ML:** CUDA unavailable, TensorFlow/PyTorch model load failures, CPU-only fallback.
- **Media/RAW:** missing source files, RAW preview failures, EXIF orientation regressions, thumbnail path problems.
- **MCP:** server not attached, SSE URL mismatch, read/write tool profile mismatch.

## Specific References

- **[DATABASE.md](DATABASE.md)** - schema and migration pointers.
- **[IMAGE_PIPELINE.md](IMAGE_PIPELINE.md)** - pipeline and RAW/NEF references.
- **[reports/DEBUGGING_SESSIONS_HUB.md](reports/DEBUGGING_SESSIONS_HUB.md)** - indexed debugging write-ups.
- **[guides/setup/DOCKER_SETUP.md](guides/setup/DOCKER_SETUP.md)** - Compose, binds, `.env` for photo paths.
- **[technical/FIREBIRD_WINDOWS_TEMPDIR.md](technical/FIREBIRD_WINDOWS_TEMPDIR.md)** - legacy Firebird on Windows temp issues.
