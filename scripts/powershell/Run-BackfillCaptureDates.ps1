# Run capture-date backfill in image-scoring-gpu-shell.
#
# Examples:
#   .\scripts\powershell\Run-BackfillCaptureDates.ps1
#   .\scripts\powershell\Run-BackfillCaptureDates.ps1 -Once -Limit 5000
#
param(
    [switch]$Once,
    [int]$Limit = 5000
)

$pyArgs = @("python", "scripts/maintenance/backfill_capture_dates.py", "--limit", "$Limit")
if ($Once) {
    $pyArgs += "--once"
}

& "$PSScriptRoot\Invoke-GpuShell.ps1" @pyArgs
exit $LASTEXITCODE
