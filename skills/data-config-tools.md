# Data and Config Tools

## Purpose
Inspect JSON, YAML, TOML-ish configs, SQLite DBs, and HTTP APIs with bounded output.

## When to Use
Use when reading package scripts, compose files, API responses, local SQLite metadata, or config migrations.

## Required Tools
jq, yq, dasel, sqlite3, curl, httpie.

## Install

### Windows PowerShell
```powershell
winget install jqlang.jq
winget install MikeFarah.yq
winget install TomWright.dasel
winget install SQLite.SQLite
winget install cURL.cURL
winget install HTTPie.HTTPie
```

### WSL2 Ubuntu
```bash
sudo apt update
sudo apt install -y jq sqlite3 curl pipx
sudo snap install yq || true
uv tool install httpie
uv tool install dasel || true
```

### macOS
```bash
brew install jq yq dasel sqlite curl httpie
```

## Common Commands
```bash
jq ".scripts" package.json
yq ".services" docker-compose.yml
dasel -f config.toml -r toml ".tool"
sqlite3 app.db ".tables"
curl -fsS http://localhost:8000/health | jq .
http --check-status GET :8000/health
```

## Agent-Safe Patterns
Pretty-print and select fields instead of dumping whole payloads. Use `curl -fsS --max-time 10`. SQLite: prefer `.schema table` and `SELECT ... LIMIT 20`.

## Commands Requiring Confirmation
Require confirmation for POST/PUT/PATCH/DELETE, DB writes, migrations, credentials in URLs, and commands uploading files.

## Troubleshooting
PowerShell has aliases for curl; use `curl.exe` if behavior differs. yq implementations differ; prefer Mike Farah yq v4.

## Verification Checklist
```bash
jq --version
yq --version
dasel --version
sqlite3 --version
curl --version
http --version
```
