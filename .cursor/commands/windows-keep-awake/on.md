# /windows-keep-awake on — Prevent Windows sleep and display timeout

Start a **detached hidden** keep-awake worker. Skill: **`.cursor/skills/windows-keep-awake/SKILL.md`**.

## Preconditions

- **Windows host** with PowerShell (not WSL).
- Repo includes **`scripts/powershell/Keep-Awake.ps1`**.

## Action (agent)

1. From **repo root** (`image-scoring-backend`), run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Keep-Awake.ps1 -Action Start
   ```

2. Confirm with:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Keep-Awake.ps1 -Action Status
   ```

3. **Report** the worker PID (or that it was already running). Do **not** use a Cursor background terminal — it aborts when the session ends.

## Done when

- `-Action Status` shows a worker PID, or start reported idempotent **already running**.
- User knows to run **`/windows-keep-awake off`** when sleep is allowed again.
