# /windows-keep-awake off — Allow Windows sleep again

Stop all keep-awake workers. Skill: **`.cursor/skills/windows-keep-awake/SKILL.md`**.

## Preconditions

- **Windows host** with PowerShell (not WSL).

## Action (agent)

1. From **repo root** (`image-scoring-backend`), run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Keep-Awake.ps1 -Action Stop
   ```

2. Confirm with:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Keep-Awake.ps1 -Action Status
   ```

3. **Report** stopped PIDs or **not running**.

## Done when

- `-Action Status` reports **Keep-awake is not running**.
