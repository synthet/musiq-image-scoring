# Troubleshooting

Hub page — follow links for specific failure modes.

## First steps

1. Run **`python scripts/doctor.py`** (WSL + `~/.venvs/tf`) — see [DIAGNOSTICS.md](DIAGNOSTICS.md).
2. If MCP is available, use **`validate_config`**, **`get_database_engine_info`**, **`check_database_health`** — see [AGENTS.md](../AGENTS.md).

## Common topics

- **[reports/DEBUGGING_SESSIONS_HUB.md](reports/DEBUGGING_SESSIONS_HUB.md)** — indexed debugging write-ups.
- **[guides/setup/DOCKER_SETUP.md](guides/setup/DOCKER_SETUP.md)** — Compose, binds, `.env` for photo paths.
- **[technical/FIREBIRD_WINDOWS_TEMPDIR.md](technical/FIREBIRD_WINDOWS_TEMPDIR.md)** — legacy Firebird on Windows temp issues.
- **[technical/MCP_DEBUGGING_TOOLS.md](technical/MCP_DEBUGGING_TOOLS.md)** — MCP workflow for jobs / DB.

## Logs

- `webui.log`, `debug.log` — see [DIAGNOSTICS.md](DIAGNOSTICS.md).

## Database

- [DATABASE.md](DATABASE.md) — schema and migration pointers.
