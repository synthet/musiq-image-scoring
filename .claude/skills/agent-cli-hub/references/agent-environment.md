# Agent environment — how Cursor uses CLI tools

Cursor does **not** maintain a separate registry of shell CLIs. Agents discover tools the same way your shell does: **if the binary is on `PATH` in the terminal session the agent uses, it can run it.**

## After installing tools

1. **Quit Cursor completely** (not just close the window).
2. Reopen the project.
3. Open a **new** integrated terminal (`Terminal → New Terminal`).
4. Run the smoke test below.

Existing terminals and agent shells may still see the old PATH until restart.

## Tool kinds

| Kind | Examples | Requirement |
|------|----------|-------------|
| **Shell CLI** | `fd`, `rg`, `bat`, `jq`, `yq`, `ruff`, `sg` | On PATH in agent shell (WSL for Python scripts) |
| **Project MCP** | `is-be-mcp`, optional `fff-be` | [`.cursor/mcp.json`](../../../mcp.example.json) + `cd mcp-server && npm run build` |
| **User MCP** | `github`, `subagent-orchestrator` | `~/.cursor/mcp.json` per [mcp.user.example.json](../../../.cursor/mcp.user.example.json) — **not** fff |
| **IDE built-in** | Grep, SemanticSearch, Glob | Always available in Cursor; no install |
| **Project-local** | `pytest`, `ruff` in WSL venvs | `~/.venvs/tf` or `~/.venvs/image-scoring-tests` |

Shell tools (`fd`, `bat`, etc.) do **not** need MCP entries.

## Smoke test (post-restart)

**Windows PowerShell** (CLI tools):

```powershell
fd --version
bat --version
sg --version
ruff --version
yq --version
```

**WSL** (backend primary):

```bash
source ~/.venvs/tf/bin/activate
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib
python scripts/doctor.py --no-gpu
ruff --version
```

If these work in the integrated terminal, the agent can use them too.

## Agent chat smoke

In a **new Agent chat**, ask:

> In WSL with ~/.venvs/tf, run `python scripts/doctor.py --no-gpu` and `fd --version` in the project root.

## Windows gotchas

### `ast-grep` / `sg` and PowerShell execution policy

npm global install may resolve as `sg.ps1`. If the agent gets "running scripts is disabled":

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Or use `sg.cmd --version` if npm created a cmd shim.

### Standalone `rg` vs Cursor-bundled ripgrep

Both are fine; the **agent shell** uses whichever comes first on PATH.

### Windows vs WSL PATH

- **Python/scripts importing `modules.*`:** WSL + `~/.venvs/tf` — see [python-wsl-webapp-env](../../../rules/python-wsl-webapp-env.mdc)
- Winget Windows installs are **not** visible inside WSL — use WSL install blocks when the agent runs in WSL
- Keep heavy repos under `~/src` when possible — see [windows-wsl-split.md](windows-wsl-split.md)

## fff MCP (project-level only)

**fff** must be configured in **project** `.cursor/mcp.json` as **`fff-be`** with `cwd` set to this git repo — user-level config fails for repo-scoped indexing.

See [AGENTS.md § fff](../../../../AGENTS.md) and [mcp.example.json](../../../mcp.example.json).

After adding fff:

1. Reload MCP in Cursor Settings.
2. Confirm `fff-be` shows connected.
3. Prefer `ffgrep` / `fffind` for repeated search; use `rg`/`fd` for one-off probes.

## Optional: log provisioning

```bash
python scripts/agent-memory/log_session.py \
  --summary "CLI tools installed per install-tiers + agent-environment" \
  --outcome "fd, bat, sg, ruff on PATH; WSL tf venv; Cursor restarted" \
  --candidate "After winget CLI installs restart Cursor so agent shells inherit PATH|working_rule|high"
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `command not found` in agent but works in old terminal | Restart Cursor; open new terminal |
| Python import fails on Windows | Use WSL + documented venv |
| MCP tools missing | Build `mcp-server/`; check `.cursor/mcp.json` |
| fff errors about home/root directory | Use **project** `fff-be` with repo `cwd` |

Install order reference: [install-tiers.md](install-tiers.md).
