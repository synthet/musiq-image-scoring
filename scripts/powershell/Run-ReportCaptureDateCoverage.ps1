# Report capture-date counts (PostgreSQL). Same env as Run-BackfillCaptureDates.ps1.
#
#   .\scripts\powershell\Run-ReportCaptureDateCoverage.ps1
#   .\scripts\powershell\Run-ReportCaptureDateCoverage.ps1 -Json
#
param(
    [switch]$Json
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

$pyArgs = if ($Json) { " --json" } else { "" }
$bashCmd = 'cd ' + $repoWsl + ' && export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib && source ~/.venvs/tf/bin/activate && python scripts/maintenance/report_capture_date_coverage.py' + $pyArgs

wsl.exe -e bash -lc $bashCmd
exit $LASTEXITCODE
