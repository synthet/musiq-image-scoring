---
description: Debug backend process — doctor, logs, WebUI, MCP status
---

## Purpose

Narrow **backend** issues: configuration, WebUI startup, log evidence, MCP attachment — without destructive DB or job actions.

## When to use

- WebUI won't start; agents cannot reach MCP; unexplained 500s; need log context.

## Canonical docs first

- [docs/DIAGNOSTICS.md](../../docs/DIAGNOSTICS.md)
- [.agent/INFRA_QUICKSTART.md](../INFRA_QUICKSTART.md)
- [AGENTS.md](../../AGENTS.md)

## Safe commands

```bash
source ~/.venvs/tf/bin/activate
python scripts/doctor.py --no-gpu
# or full: python scripts/doctor.py
```

- Tail logs per DIAGNOSTICS.md (`webui.log`, `debug.log`).
- With WebUI running: HTTP `GET /mcp-status` — MCP route and `expected_sse_url` (see `webui.py`).
- MCP log search (when server enabled): tools `search_logs`, `get_server_log_tail`, `read_debug_log` — see [workflows/safe_mcp_diagnostics.md](safe_mcp_diagnostics.md).

## Files commonly touched (when implementing fixes)

- `webui.py`, `modules/config.py`, `modules/api.py` — only after root cause is known.

## Common failure modes

- Wrong port; firewall; WSL vs Windows URL mismatch.
- Postgres down; `database.engine` mis-set.

## Do not

- Do not enable `execute_code` on shared hosts without understanding it runs in the WebUI process.
- Do not paste secrets into MCP or logs.
