# MCP tool reference — subagent-orchestrator

Server display name: **subagent-orchestrator**

Project MCP keys: **`imgscore-subagent-orchestrator`** (backend), **`imgscore-el-subagent-orchestrator`** (gallery).

## detect_subagents

No parameters.

**Example response (shape):**

```json
{
  "agents": {
    "codex": {
      "available": true,
      "command": "codex",
      "mode": "exec",
      "version": "…",
      "notes": []
    },
    "gemini": {
      "available": true,
      "command": "gemini",
      "mode": "prompt",
      "version": "…",
      "notes": []
    },
    "claude": {
      "available": true,
      "command": "claude",
      "mode": "print",
      "version": "…",
      "notes": []
    }
  },
  "detectedAt": "2026-05-27T…"
}
```

## run_subagent

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `agent` | `"codex"` \| `"gemini"` \| `"claude"` | yes | — | Prefer codex/gemini for live runs |
| `task` | string | yes | — | Max 8000 chars |
| `files` | string[] | no | — | Workspace-relative; max 20 |
| `mode` | `review` \| `implement` \| `explain` \| `test` \| `tie-breaker` | no | `review` | |
| `timeoutMs` | number | no | 300000 | Max 900000 |
| `allowWrites` | boolean | no | `false` | **Rejected in v0.1** |
| `dryRun` | boolean | no | `false` | Command preview only |
| `extraContext` | string | no | — | Max 4000 chars |

**Example — dry run (backend):**

```json
{
  "agent": "codex",
  "task": "Review modules/api.py changes for REST contract drift",
  "files": ["modules/api.py"],
  "mode": "review",
  "allowWrites": false,
  "dryRun": true
}
```

**Example — live review (gallery):**

```json
{
  "agent": "gemini",
  "task": "Review electron/db.ts IPC exposure for renderer safety",
  "files": ["electron/db.ts", "electron/preload.ts"],
  "mode": "review",
  "allowWrites": false
}
```

**Example response (shape):**

```json
{
  "ok": true,
  "agent": "codex",
  "exitCode": 0,
  "durationMs": 18422,
  "outputFile": ".agent-runs/20260526-203012-codex-review-api/stdout.md",
  "outputDir": ".agent-runs/20260526-203012-codex-review-api",
  "summary": "…",
  "commandPreview": "codex exec --sandbox read-only …"
}
```

## On-disk artifacts

```text
.agent-runs/YYYYMMDD-HHMMSS-<agent>-<slug>/
  request.json
  stdout.md
  stderr.log
  result.json
```

Written under the **active workspace** (backend or gallery), not under `subagent-orchestrator`.
