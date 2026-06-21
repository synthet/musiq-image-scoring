---
name: windows-keep-awake
description: Prevent Windows sleep and display timeout via SetThreadExecutionState. Use when the user asks to keep Windows awake, pause sleep, prevent screen off, or stop sleep during long jobs. Starts a detached hidden PowerShell worker (not a Cursor background terminal).
---

# windows-keep-awake

## Role

Run **`scripts/powershell/Keep-Awake.ps1`** from **repo root** (or any cwd — script resolves its own path). Prevents **system sleep** and **display timeout** until explicitly stopped.

## When to use

- User says: keep awake, pause sleep, prevent sleep, don't sleep, keep screen on, etc.
- Long local jobs (backfills, downloads, builds) where Windows power settings would interrupt work.

## Start (canonical)

**Always** use the script with `-Action Start`. It launches a **hidden detached** `powershell.exe` child (`Start-Process`), not a Cursor background terminal — background terminals abort when the session ends and sleep prevention stops.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Keep-Awake.ps1 -Action Start
```

Confirm with `-Action Status` or report the PID printed on start.

## Stop

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Keep-Awake.ps1 -Action Stop
```

## Status

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Keep-Awake.ps1 -Action Status
```

## Implementation notes (avoid prior failures)

| Pitfall | Fix |
|---------|-----|
| Inline `Add-Type` with nested quoting in a one-liner | Use the script file; C# constants live in `Invoke-KeepAwakeLoop` |
| Passing `0x80000003` from PowerShell | Define `ES_*` flags in C# and OR them there — PowerShell treats the hex literal as signed int32 |
| Cursor `block_until_ms: 0` background shell | Use `Start-Process -WindowStyle Hidden` via the script's `-Action Start` |
| Multiple restarts | `-Action Start` is idempotent; `-Action Stop` kills all `-Action Worker` processes |

## Success criteria

- `-Action Status` shows one worker PID (or start reported a PID).
- Windows does not sleep or turn off the display while the worker runs.
- `-Action Stop` clears all worker PIDs.

## Guardrails

- **Windows only** — do not use on WSL/Linux/macOS.
- Stop the worker when the user no longer needs wake lock (battery, overnight, etc.).
- Do not commit transient `.keep-awake.ps1` at repo root; the canonical script is under `scripts/powershell/`.
