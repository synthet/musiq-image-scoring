<#
.SYNOPSIS
    Ensures the Docker daemon is reachable; starts Docker Desktop on Windows if needed.
.DESCRIPTION
    Used by docker_refresh_webui.bat and related launchers. Polls "docker info" until
    the daemon responds or the timeout elapses. Set SKIP_DOCKER_START=1 to only wait
    (do not launch Docker Desktop).
.PARAMETER TimeoutSec
    Maximum seconds to wait for the daemon after a start attempt (default 180).
.EXAMPLE
    .\Ensure-DockerDesktop.ps1 -TimeoutSec 240
#>
[CmdletBinding()]
param(
    [int]$TimeoutSec = 180
)

$ErrorActionPreference = 'Continue'

function Test-DockerDaemonReady {
    $null = docker info 2>&1
    return $LASTEXITCODE -eq 0
}

if (Test-DockerDaemonReady) {
    exit 0
}

if ($env:SKIP_DOCKER_START -eq '1') {
    Write-Host '[ERROR] Docker daemon is not running (SKIP_DOCKER_START=1; not attempting to start Docker Desktop).'
    exit 1
}

$started = $false
$dockerCli = Get-Command docker -ErrorAction SilentlyContinue
if ($dockerCli) {
    Write-Host '[INFO] Starting Docker Desktop via: docker desktop start'
    docker desktop start 2>&1 | ForEach-Object { Write-Host "  $_" }
    if ($LASTEXITCODE -eq 0) {
        $started = $true
    } else {
        Write-Host '[WARN] "docker desktop start" failed or is unavailable; trying Docker Desktop.exe...'
    }
}

if (-not $started) {
    $candidates = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Docker\Docker\Docker Desktop.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Docker\Docker\Docker Desktop.exe')
    )
    $desktopExe = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $desktopExe) {
        Write-Host '[ERROR] Docker Desktop is not running and its executable was not found.'
        Write-Host '        Install Docker Desktop or start it manually, then re-run this script.'
        exit 1
    }
    Write-Host "[INFO] Launching: $desktopExe"
    Start-Process -FilePath $desktopExe | Out-Null
}

if ($TimeoutSec -lt 30) { $TimeoutSec = 30 }

Write-Host "[INFO] Waiting for Docker daemon (up to ${TimeoutSec}s)..."
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$dots = 0
while ((Get-Date) -lt $deadline) {
    if (Test-DockerDaemonReady) {
        Write-Host '[OK] Docker daemon is ready.'
        exit 0
    }
    Start-Sleep -Seconds 2
    $dots = ($dots + 1) % 15
    if ($dots -eq 0) {
        $remaining = [math]::Max(0, [int]($deadline - (Get-Date)).TotalSeconds)
        Write-Host "  ... still waiting (${remaining}s left)"
    }
}

Write-Host "[ERROR] Docker daemon did not become ready within ${TimeoutSec}s."
Write-Host '        Check Docker Desktop in the system tray or run: docker desktop status'
exit 1
