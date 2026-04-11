# Run capture-date backfill in WSL with ~/.venvs/tf (same env as run_webui.bat).
# Do not paste bash "export ... &&" lines into PowerShell — use this script or:
#   wsl.exe -e bash -lc 'cd /mnt/d/Projects/image-scoring-backend && ...'
#
# Examples:
#   .\scripts\powershell\Run-BackfillCaptureDates.ps1
#   .\scripts\powershell\Run-BackfillCaptureDates.ps1 -Once -Limit 5000
#
param(
    [switch]$Once,
    [int]$Limit = 5000
)

function Convert-ToWslPath {
    param([string]$WindowsPath)
    $p = $WindowsPath -replace '\\', '/'
    if ($p -match '^([A-Za-z]):/(.*)$') {
        $drive = $Matches[1].ToLower()
        $rest = $Matches[2]
        return "/mnt/$drive/$rest"
    }
    return $p
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$repoWsl = Convert-ToWslPath $repoRoot.Path

$pyArgs = if ($Once) { " --once --limit $Limit" } else { " --limit $Limit" }

# Single-quoted pieces so $LD_LIBRARY_PATH and $(pwd) are interpreted by bash, not PowerShell.
$bashCmd = 'cd ' + $repoWsl + ' && export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib && source ~/.venvs/tf/bin/activate && python scripts/maintenance/backfill_capture_dates.py' + $pyArgs

Write-Host "WSL repo: $repoWsl"
Write-Host "Running in WSL bash..."
Write-Host ""

wsl.exe -e bash -lc $bashCmd
exit $LASTEXITCODE
