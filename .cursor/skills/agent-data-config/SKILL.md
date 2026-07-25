---
name: agent-data-config
description: >-
  Inspect JSON, YAML, and API responses with jq, yq, dasel, curl, and httpie.
  Use for package.json, config.json, and backend health checks. Never output
  secrets or full credential-bearing config.
---

# Agent data and config tools

Bounded inspection of structured data and HTTP endpoints.

## Purpose

Query JSON/YAML/TOML and probe APIs without dumping large or sensitive files.

## When to use

- Reading `package.json` scripts or dependencies
- Inspecting `config.json` keys (engine, API URL) — **redact secrets**
- Probing backend health (`http://localhost:7860`) when debugging gallery connectivity
- SQLite queries for local diagnostics (when applicable)

## Required tools

`jq`, optional `yq`, `dasel`, `curl` or `httpie`, optional `sqlite3`

Install: [agent-cli-hub/references/install-blocks.md](../agent-cli-hub/references/install-blocks.md)

## Common commands

### package.json (gallery)

```bash
jq '.scripts' package.json
jq '.devDependencies | keys' package.json
jq -r '.scripts.dev' package.json
```

### config.json (redact before sharing)

```bash
jq '.database.engine' config.json
jq '.api // empty' config.json
jq 'del(.database.postgres.password) | .database' config.json
```

### YAML (if present)

```bash
yq '.services' docker-compose.yml
```

### Backend reachability

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:7860/api/health
curl -s http://localhost:7860/mcp-status | jq .
```

PowerShell:

```powershell
Get-Content package.json | jq '.scripts'
Invoke-WebRequest -Uri http://localhost:7860/api/health -UseBasicParsing
```

### PowerShell JSON POST (file body)

Inline `curl.exe -d "{\"k\":1}"` is corrupted by PowerShell quoting (`json_invalid` / bad range errors). Write the body to a file and use `--data-binary`:

```powershell
Set-Content -Encoding ascii -Path "$env:TEMP\body.json" -Value '{"limit":50,"target_phases":["bird_species"]}'
curl.exe -sS -m 30 -X POST "http://127.0.0.1:7860/api/runs/drive/start" `
  -H "Content-Type: application/json" --data-binary "@$env:TEMP\body.json"
```

Prefer `curl.exe` over `Invoke-RestMethod` for POST bodies. For large or multi-endpoint responses, write each response to its own file and parse with `jq` / `python -c` — concatenated stdout does not parse as a single JSON document.

## Agent-safe patterns

- Select fields with `jq` — do not `cat config.json` into chat if it may hold passwords.
- Bound HTTP output: status codes, single JSON keys, not full HTML pages.
- Prefer `npm run doctor` for gallery config/backend discovery when available.

## Commands requiring confirmation

- POST/PUT/DELETE to production APIs without user approval
- Exporting database dumps containing user media metadata at scale

See [`.agent/SAFETY.md`](../../../.agent/SAFETY.md).

## Troubleshooting

- **Invalid JSON:** `jq empty config.json` to validate; file may be gitignored — check `config.example.json` if present
- **Backend connection refused:** verify sibling backend running; see `.agent/workflows/debug_gallery_backend_connection.md`
- **PowerShell POST `json_invalid`:** do not inline JSON in `-d "..."`; use the file-body pattern above.

## Verification checklist

```bash
jq --version
jq '.name' package.json
```
