<#
.SYNOPSIS
    Run a command inside image-scoring-gpu-shell (Compose profile gpu-shell).

.DESCRIPTION
    Ensures db + gpu-shell are up, converts Windows paths in arguments to
    container paths (/app for this repo, /mnt/<drive>/... otherwise), then
    docker exec's the command with working directory /app.

    This is the canonical runner for scripts / modules.* / ML now that Ubuntu
    WSL is optional. WebUI stays on image-scoring-webui; pytest -m wsl still
    needs Ubuntu + ~/.venvs/image-scoring-tests when that distro exists.

.PARAMETER Detach
    docker exec -d (long jobs). Do not use with stdio MCP.

.PARAMETER Interactive
    docker exec -it (TTY). For interactive bash only.

.PARAMETER Env
    Extra -e KEY=VALUE pairs (repeatable).

.PARAMETER ArgList
    Command and args, e.g. python scripts/doctor.py --no-gpu

.EXAMPLE
    .\scripts\powershell\Invoke-GpuShell.ps1 python scripts/doctor.py --no-gpu
    .\scripts\powershell\Invoke-GpuShell.ps1 -Detach python scripts/backfill_bird_bbox.py --all-null
    .\scripts\powershell\Invoke-GpuShell.ps1 -Env ENABLE_MCP_SERVER=1 python -m modules.mcp_server
#>
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$ArgList,
    [switch]$Detach,
    [switch]$Interactive,
    [string[]]$Env = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $ArgList -or $ArgList.Count -eq 0) {
    throw "Usage: Invoke-GpuShell.ps1 [-Detach] [-Interactive] [-Env KEY=VAL] <command> [args...]"
}

if ($env:GPU_SHELL_DETACH -eq "1") {
    $Detach = $true
}

if ($ArgList.Count -gt 0 -and $ArgList[0] -eq "--") {
    $ArgList = @($ArgList | Select-Object -Skip 1)
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Convert-GpuShellArg {
    param(
        [string]$Arg,
        [string]$RepoRoot
    )
    if ([string]::IsNullOrEmpty($Arg)) {
        return $Arg
    }
    $repoNorm = $RepoRoot.TrimEnd("\", "/")
    if ($Arg -match '^[A-Za-z]:[\\/]') {
        $full = $Arg
        try {
            $resolved = Resolve-Path -LiteralPath $Arg -ErrorAction Stop
            $full = $resolved.Path
        }
        catch {
            $full = $Arg
        }
        if ($full.StartsWith($repoNorm, [System.StringComparison]::OrdinalIgnoreCase)) {
            $rel = $full.Substring($repoNorm.Length).TrimStart("\", "/").Replace("\", "/")
            if ([string]::IsNullOrEmpty($rel)) {
                return "/app"
            }
            return "/app/$rel"
        }
        $drive = $Arg.Substring(0, 1).ToLowerInvariant()
        $rest = $Arg.Substring(2).Replace("\", "/")
        if (-not $rest.StartsWith("/")) {
            $rest = "/$rest"
        }
        return "/mnt/$drive$rest"
    }
    if ($Arg.Contains("\")) {
        return $Arg.Replace("\", "/")
    }
    return $Arg
}

function Test-DockerReady {
    & docker info 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker daemon not ready. Start Docker Desktop and retry."
    }
}

Test-DockerReady

Push-Location $RepoRoot
try {
    & docker compose --profile gpu-shell up -d db gpu-shell
    if ($LASTEXITCODE -ne 0) {
        throw "compose up failed. Build first: docker compose build webui"
    }
}
finally {
    Pop-Location
}

$converted = foreach ($arg in $ArgList) {
    Convert-GpuShellArg -Arg $arg -RepoRoot $RepoRoot
}

$execArgs = [System.Collections.Generic.List[string]]::new()
[void]$execArgs.Add("exec")
[void]$execArgs.Add("-w")
[void]$execArgs.Add("/app")
[void]$execArgs.Add("-e")
[void]$execArgs.Add("PYTHONPATH=/app")
if ($Detach) {
    [void]$execArgs.Add("-d")
}
elseif ($Interactive) {
    [void]$execArgs.Add("-it")
}
else {
    [void]$execArgs.Add("-i")
}
foreach ($pair in $Env) {
    [void]$execArgs.Add("-e")
    [void]$execArgs.Add($pair)
}
[void]$execArgs.Add("image-scoring-gpu-shell")
foreach ($arg in $converted) {
    [void]$execArgs.Add($arg)
}

& docker @($execArgs.ToArray())
# Do not `exit` — that kills callers such as Run-Scoring.ps1. Bats append `; exit $LASTEXITCODE`.
