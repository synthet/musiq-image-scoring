# Report capture-date counts (PostgreSQL). Same env as Run-BackfillCaptureDates.ps1.
#
#   .\scripts\powershell\Run-ReportCaptureDateCoverage.ps1
#   .\scripts\powershell\Run-ReportCaptureDateCoverage.ps1 -Json
#
param(
    [switch]$Json
)

$pyArgs = @("python", "scripts/maintenance/report_capture_date_coverage.py")
if ($Json) {
    $pyArgs += "--json"
}

& "$PSScriptRoot\Invoke-GpuShell.ps1" @pyArgs
exit $LASTEXITCODE
