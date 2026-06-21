---
type: Guide
title: Agent cull review — Antigravity / Gemini CLI setup
description: Operator guide for enabling agent-assisted cull review when the backend WebUI runs in Docker, WSL, or Windows native.
resource: docs/guides/setup/agent-cull-review-gemini-cli.md
tags: [guides, setup, culling, agent-cull-review, antigravity, gemini, docker, gallery-docs]
timestamp: 2026-06-20T00:00:00Z
okf_version: 0.1
---

# Agent cull review — Antigravity / Gemini CLI setup

Enable **agent-assisted cull review** (`culling.agent_review` in `config.json`) so the backend can spawn an external CLI for vision redundancy checks on small stack/substack groups. The Gallery **Agent cull review** panel calls `POST /api/culling/agent-review/run`.

**Default (June 2026+):** [Antigravity CLI](https://antigravity.google/download#antigravity-cli) (`agy`) — Google’s replacement for individual **Gemini CLI** sign-in. **Legacy:** Gemini CLI with an API key still works via `provider: gemini`.

**Related:** [agent-assisted cull review spec](../../specs/agent-assisted-cull-review/INDEX.md) · Gallery panel: [`AgentCullReviewPanel`](https://github.com/synthet/image-scoring-gallery/blob/main/src/components/CullingAnalytics/AgentCullReviewPanel.tsx)

## Prerequisites

- `culling.agent_review.enabled: true` in `config.json`
- `alembic upgrade head` applied (migration `0031_agent_cull_recommendations`)
- CLI installed and authenticated on the **host** (or API key in Docker `.env`)

## Runtime matrix

`culling.agent_review.agent.command` must be valid **for the OS that runs the WebUI Python process**.

| WebUI launcher | Process OS | Recommended setup |
|----------------|------------|-------------------|
| `docker compose up` / `docker_refresh_webui.bat` | Linux (container) | `provider: antigravity`, `command: /app/scripts/wsl/antigravity_agent.sh` |
| `run_webui.bat` / WSL `python launch.py` | WSL Linux | Full WSL path to `scripts/wsl/antigravity_agent.sh` |
| `run_webui_windows.bat` | Windows | `agy` on PATH or full path to `%LOCALAPPDATA%\agy\bin\agy.exe` |

**Common mistake:** Host paths like `/mnt/d/Projects/...` while WebUI runs in **Docker** — inside the container the repo is `/app`.

---

## Path B — Antigravity CLI (recommended)

Google retired **Gemini Code Assist for individuals** in Gemini CLI ([developers blog](https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/)). Use **Antigravity CLI** instead.

### 1. Install on the Windows host

From [antigravity.google/download#antigravity-cli](https://antigravity.google/download#antigravity-cli):

```powershell
irm https://antigravity.google/cli/install.ps1 | iex
agy --version
```

Open a **new** terminal so `PATH` includes `%LOCALAPPDATA%\agy\bin`.

### 2. Authenticate on the host (once)

Run `agy` interactively and complete the browser sign-in (first launch prompts OAuth):

```powershell
agy -p "hello"
```

Credentials land under `%USERPROFILE%\.gemini\antigravity-cli\` (mounted into Docker as `/root/.gemini`).

**Headless / API key alternative:** set in `.env` beside `docker-compose.yml`:

```env
GEMINI_API_KEY=your_ai_studio_key
# or
ANTIGRAVITY_API_KEY=your_ai_studio_key
```

Create keys at [Google AI Studio](https://aistudio.google.com/apikey).

### 3. Configure `.env` (Docker)

```env
GEMINI_CONFIG_SOURCE=C:/Users/you/.gemini
# optional if using API key only:
# GEMINI_API_KEY=...
```

Use forward slashes. See [`.env.example`](../../../.env.example).

### 4. Set `config.json`

```json
"culling": {
  "agent_review": {
    "enabled": true,
    "agent": {
      "provider": "antigravity",
      "command": "/app/scripts/wsl/antigravity_agent.sh"
    }
  }
}
```

`antigravity_agent.sh` runs `agy -p <prompt> --dangerously-skip-permissions` and uses a PTY wrapper on Linux when needed for subprocess capture.

### 5. Rebuild WebUI image (includes `agy`)

```bash
docker compose build webui
docker compose up -d webui
```

Windows: **`docker_refresh_webui.bat`** (frontend + image rebuild + verify).

### 6. Verify inside the container

```bash
docker exec image-scoring-webui agy --version
docker exec image-scoring-webui test -d /root/.gemini && echo config_mount_ok
docker exec image-scoring-webui /app/scripts/wsl/antigravity_agent.sh --version
```

---

## Path A — Legacy Gemini CLI (API key)

Use when you prefer `gemini` over `agy` (still supported).

1. `npm install -g @google/gemini-cli`
2. `gemini auth` → choose **2. Use Gemini API Key** (option 1 Google sign-in is blocked for individuals)
3. `provider: gemini`, `command: /app/scripts/wsl/gemini_agent.sh`
4. Same `GEMINI_CONFIG_SOURCE` / `GEMINI_API_KEY` mount as above

---

## Compose environment (reference)

| Variable | Set in | Purpose |
|----------|--------|---------|
| `GEMINI_CONFIG_SOURCE` | `.env` | Host `~/.gemini` → `/root/.gemini` (Antigravity + legacy Gemini creds) |
| `GEMINI_API_KEY` | `.env` | Headless auth for `agy` / `gemini` in container |
| `ANTIGRAVITY_API_KEY` | `.env` | Same as above (alias accepted by Antigravity CLI) |
| `GEMINI_CLI_TRUST_WORKSPACE` | `docker-compose.yml` | Legacy Gemini headless trust |
| `DOCKER_CONTAINER` | `docker-compose.yml` | Docker branch in bridge scripts |

## CLI adapter behaviour

Implementation: [`modules/agent_cull/cli_adapter.py`](../../../modules/agent_cull/cli_adapter.py)

| `provider` | Invocation | stdout unwrap |
|------------|------------|---------------|
| `antigravity` | `antigravity_agent.sh <prompt>` → `agy -p …` | ANSI strip + JSON extract |
| `gemini` | `gemini --skip-trust --output-format json -p <prompt>` | `.response` envelope |
| `codex` | `codex exec --sandbox <read-only\|workspace> --ask-for-approval never --json <prompt>` | raw JSON |
| `claude` | `claude_agent.sh -p --output-format json --dangerously-skip-permissions <prompt>` | `.result` envelope |
| `cursor` | `cursor_agent.sh -p --output-format json <prompt>` | `.result` envelope |

All normalize stdout to agent JSON before schema validation. `codex` runs as the bare `codex` binary (no bridge script). `claude` / `cursor` use the thin `scripts/wsl/{claude,cursor}_agent.sh` bridges (Docker exec + WSL `cmd.exe` forward, like `gemini_agent.sh`); both read thumbnail files for vision via the image paths in the packet, so the CLI only needs to be **authenticated on PATH** for the WebUI process (claude additionally runs `--dangerously-skip-permissions` so the unattended process may read those files). For the **Docker** runtime the `claude` / `cursor-agent` binary must be installed in the image and pre-authenticated, exactly as `agy` / `gemini` are today.

Operator debug:

```bash
PYTHONPATH=/app python3 scripts/agent_cull_review.py --stack-id <id> --sub-stack-id <id> --dry-run --json --force
```

## Verify vision (Docker)

After a dry-run, inspect persisted `request_json` on `agent_cull_review_groups`: `thumbnail_manifest` paths should be under `/app/thumbnails/...`, not host-only `/mnt/d/...`.

Smoke-test `agy` can read a manifest path:

```bash
docker exec image-scoring-webui /root/.local/bin/agy -p "Read /app/thumbnails/ab/<hash>.jpg and reply JSON {description, species}" --dangerously-skip-permissions
```

Packet probe (optional):

```bash
docker exec image-scoring-webui env PYTHONPATH=/app python3 /app/.agent/tmp/probe_agent_packet.py <stack_id>
```

## Gallery error messages

| Code | Meaning | Fix |
|------|---------|-----|
| `agent_cli_not_found` | Bridge script / `agy` missing | Rebuild image; check `command` path |
| `agent_cli_auth_failed` | Not authenticated in container | Host `agy` login + `GEMINI_CONFIG_SOURCE`, or API key in `.env` |
| `agent_cli_auth_tier` | Legacy Gemini Google sign-in blocked | Migrate to Antigravity or Gemini API key |
| `agent_review_disabled` | `enabled: false` | Set `culling.agent_review.enabled: true` |
| `schema_invalid` | CLI ran but JSON failed validation | Check `response_raw` on failed group |
| `timeout` | Exceeded `agent.timeout_seconds` (default 120) | Retry; increase timeout |

## Related pages

- [Agent-assisted cull review — summary](../../specs/agent-assisted-cull-review/summary.md)
- [DOCKER_SETUP.md](DOCKER_SETUP.md)
