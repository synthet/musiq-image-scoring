<#
.SYNOPSIS
    Dumps the image_scoring PostgreSQL database to a local backup folder.

.DESCRIPTION
    Runs pg_dump against the Postgres instance defined in config.json.
    Tries a locally installed pg_dump.exe first; falls back to docker exec
    into the image-scoring-postgres container if no local binary is found.
    Old dumps are pruned by -MaxBackups (count, newest kept) and/or -RetentionDays (age).

.PARAMETER ConfigPath
    Path to config.json. Defaults to two levels above this script (project root).

.PARAMETER BackupDir
    Destination folder for .dump files.
    Defaults to <project root>\backups\postgres.

.PARAMETER RetentionDays
    Delete dumps older than this many days in -BackupDir. Set to 0 to skip age cleanup.
    Default: 30.

.PARAMETER MaxBackups
    Keep at most this many newest dumps in -BackupDir. Set to 0 to skip count cleanup.

.PARAMETER MirrorDir
    If set, copy the finished .dump here (e.g. Dropbox). Empty skips mirror.

.PARAMETER MirrorRetentionDays
    When -MirrorDir is set, delete mirror copies of ${dbname}_*.dump older than this many days.
    Set to 0 to skip mirror age cleanup. Default: 7.

.PARAMETER MirrorMaxBackups
    When -MirrorDir is set, keep at most this many newest mirror dumps. Set to 0 to skip.

.EXAMPLE
    .\Backup-Postgres.ps1
    .\Backup-Postgres.ps1 -RetentionDays 7
    .\Backup-Postgres.ps1 -BackupDir D:\Backups\postgres -RetentionDays 0
    .\Backup-Postgres.ps1 -MirrorDir "D:\Dropbox\Photos\Scoring" -MirrorRetentionDays 7
    .\Backup-Postgres.ps1 -MaxBackups 3 -MirrorDir "D:\Dropbox\Photos\Scoring" -MirrorMaxBackups 3 -RetentionDays 0 -MirrorRetentionDays 0
#>
[CmdletBinding()]
param(
    [string]$ConfigPath   = $null,
    [string]$BackupDir    = $null,
    [int]   $RetentionDays = 30,
    [int]   $MaxBackups = 0,
    [string]$MirrorDir    = $null,
    [int]   $MirrorRetentionDays = 7,
    [int]   $MirrorMaxBackups = 0
)

if ([string]::IsNullOrEmpty($PSScriptRoot)) {
    $PSScriptRoot = Split-Path -Parent -Path $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrEmpty($ConfigPath)) {
    $ConfigPath = Join-Path $PSScriptRoot "..\..\config.json"
}
if ([string]::IsNullOrEmpty($BackupDir)) {
    $BackupDir = Join-Path $PSScriptRoot "..\..\backups\postgres"
}

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Step([string]$msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $msg" -ForegroundColor Cyan
}

function Write-OK([string]$msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] OK  $msg" -ForegroundColor Green
}

function Write-Fail([string]$msg) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ERR $msg" -ForegroundColor Red
}

function Invoke-PruneDumpBackupsByCount {
    param(
        [string]$Dir,
        [string]$Filter,
        [int]$MaxBackups,
        [string]$Label = "dump"
    )
    if ($MaxBackups -le 0) {
        return 0
    }
    $files = @(Get-ChildItem -Path $Dir -Filter $Filter -File | Sort-Object LastWriteTime -Descending)
    $pruned = 0
    if ($files.Count -gt $MaxBackups) {
        $files | Select-Object -Skip $MaxBackups | ForEach-Object {
            Write-Host "    Removing ($Label): $($_.Name)"
            Remove-Item $_.FullName -Force
            $pruned++
        }
    }
    return $pruned
}

# ---------------------------------------------------------------------------
# Load connection config (config.json merged with environment.json via Python)
# ---------------------------------------------------------------------------

Write-Step "Resolving config path: $ConfigPath"

$ConfigPath = (Resolve-Path $ConfigPath).Path
$ProjectRoot = Split-Path -Parent $ConfigPath

$cfgJson = $null
try {
    $pyCode = @"
import json, sys
sys.path.insert(0, r'$ProjectRoot')
from modules.config import load_config
print(json.dumps(load_config()))
"@
    $cfgJson = & python -c $pyCode 2>$null
} catch {
    $cfgJson = $null
}

if (-not $cfgJson) {
    Write-Host "    Warning: merged config unavailable (is Python on PATH?). Reading config.json only." -ForegroundColor Yellow
    $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
} else {
    $cfg = $cfgJson | ConvertFrom-Json
}

$pgCfg  = $cfg.database.postgres
$PgHost = if ($pgCfg.host)     { $pgCfg.host }     else { "127.0.0.1" }
$PgPort = if ($pgCfg.port)     { [string]$pgCfg.port } else { "5432" }
$PgDb   = if ($pgCfg.dbname)   { $pgCfg.dbname }   else { "image_scoring" }
$PgUser = if ($pgCfg.user)     { $pgCfg.user }     else { "postgres" }
$PgPass = if ($pgCfg.password) { $pgCfg.password } else { "postgres" }

Write-Host "    host=$PgHost  port=$PgPort  db=$PgDb  user=$PgUser"

# ---------------------------------------------------------------------------
# Resolve backup directory
# ---------------------------------------------------------------------------

$BackupDir = [System.IO.Path]::GetFullPath($BackupDir)
if (-not (Test-Path $BackupDir)) {
    Write-Step "Creating backup directory: $BackupDir"
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

$Timestamp  = Get-Date -Format "yyyyMMdd_HHmmss"
$DumpFile   = Join-Path $BackupDir "${PgDb}_${Timestamp}.dump"

Write-Step "Backup destination: $DumpFile"

# ---------------------------------------------------------------------------
# Locate pg_dump (local first, then docker exec fallback)
# ---------------------------------------------------------------------------

$pgDumpExe = $null

# 1. Check PATH
$found = Get-Command pg_dump.exe -ErrorAction SilentlyContinue
if ($found) {
    $pgDumpExe = $found.Source
}

# 2. Common pgAdmin / EDB installation paths
if (-not $pgDumpExe) {
    $searchRoots = @(
        "C:\Program Files\PostgreSQL",
        "C:\Program Files (x86)\PostgreSQL",
        "$env:LOCALAPPDATA\Programs\pgAdmin 4"
    )
    foreach ($root in $searchRoots) {
        if (Test-Path $root) {
            $hit = Get-ChildItem -Path $root -Recurse -Filter "pg_dump.exe" -ErrorAction SilentlyContinue |
                   Sort-Object FullName -Descending |
                   Select-Object -First 1
            if ($hit) {
                $pgDumpExe = $hit.FullName
                break
            }
        }
    }
}

$useDocker = $false
if ($pgDumpExe) {
    Write-OK "Found local pg_dump: $pgDumpExe"
} else {
    Write-Step "No local pg_dump found - will use docker exec fallback"
    # Verify docker is available and the container is running
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Fail "Neither pg_dump nor docker is available on PATH. Cannot continue."
        exit 1
    }
    $containerState = docker inspect --format "{{.State.Status}}" image-scoring-postgres 2>&1
    if ($containerState -ne "running") {
        Write-Fail "Container 'image-scoring-postgres' is not running (state: $containerState). Start it with: docker-compose -f docker-compose.postgres.yml up -d"
        exit 1
    }
    $useDocker = $true
}

# ---------------------------------------------------------------------------
# Run pg_dump
# ---------------------------------------------------------------------------

Write-Step "Running pg_dump (format: custom)..."

$env:PGPASSWORD = $PgPass

try {
    if ($useDocker) {
        # Write dump inside the container, then docker cp (reliable binary; avoids broken stdout capture on Windows)
        $containerTmp = "/tmp/${PgDb}_${Timestamp}.dump"
        $dumpArgs = @(
            "exec",
            "-e", "PGPASSWORD=$PgPass",
            "image-scoring-postgres",
            "pg_dump",
            "--host=$PgHost",
            "--port=$PgPort",
            "--username=$PgUser",
            "--dbname=$PgDb",
            "--format=custom",
            "--no-password",
            "--file=$containerTmp"
        )
        Write-Host "    docker $($dumpArgs -join ' ')"
        & docker @dumpArgs
        if ($LASTEXITCODE -ne 0) {
            throw "docker exec pg_dump exited with code $LASTEXITCODE"
        }
        Write-Step "Copying dump from container to host..."
        & docker cp "image-scoring-postgres:${containerTmp}" $DumpFile
        if ($LASTEXITCODE -ne 0) {
            throw "docker cp exited with code $LASTEXITCODE"
        }
        & docker exec image-scoring-postgres rm -f $containerTmp
    } else {
        $pgArgs = @(
            "--host=$PgHost",
            "--port=$PgPort",
            "--username=$PgUser",
            "--dbname=$PgDb",
            "--format=custom",
            "--no-password",
            "--file=$DumpFile"
        )
        Write-Host "    $pgDumpExe $($pgArgs -join ' ')"
        & $pgDumpExe @pgArgs
        if ($LASTEXITCODE -ne 0) {
            throw "pg_dump exited with code $LASTEXITCODE"
        }
    }
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

# Verify the dump file was actually written
if (-not (Test-Path $DumpFile) -or (Get-Item $DumpFile).Length -eq 0) {
    Write-Fail "Dump file is missing or empty: $DumpFile"
    exit 1
}

$sizeMB = [math]::Round((Get-Item $DumpFile).Length / 1MB, 2)
Write-OK ('Dump complete: {0} ({1} MB)' -f $DumpFile, $sizeMB)

# ---------------------------------------------------------------------------
# Optional mirror copy (e.g. Dropbox) + mirror retention
# ---------------------------------------------------------------------------

if (-not [string]::IsNullOrWhiteSpace($MirrorDir)) {
    $MirrorDir = [System.IO.Path]::GetFullPath($MirrorDir.Trim())
    if (-not (Test-Path $MirrorDir)) {
        Write-Step "Creating mirror directory: $MirrorDir"
        New-Item -ItemType Directory -Path $MirrorDir -Force | Out-Null
    }
    $mirrorFile = Join-Path $MirrorDir ([System.IO.Path]::GetFileName($DumpFile))
    Write-Step "Copying dump to mirror: $mirrorFile"
    Copy-Item -LiteralPath $DumpFile -Destination $mirrorFile -Force
    if (-not (Test-Path $mirrorFile) -or (Get-Item $mirrorFile).Length -eq 0) {
        Write-Fail "Mirror copy missing or empty: $mirrorFile"
        exit 1
    }
    $mMB = [math]::Round((Get-Item $mirrorFile).Length / 1MB, 2)
    Write-OK ('Mirror copy complete: {0} ({1} MB)' -f $mirrorFile, $mMB)

    if ($MirrorMaxBackups -gt 0) {
        Write-Step "Pruning mirror dumps (keep newest $MirrorMaxBackups)..."
        $mPruned = Invoke-PruneDumpBackupsByCount -Dir $MirrorDir -Filter "${PgDb}_*.dump" -MaxBackups $MirrorMaxBackups -Label "mirror"
        if ($mPruned -eq 0) {
            Write-Host "    Nothing to prune in mirror."
        } else {
            Write-OK "Pruned $mPruned old dump(s) from mirror."
        }
    } elseif ($MirrorRetentionDays -gt 0) {
        Write-Step "Pruning mirror dumps older than $MirrorRetentionDays days..."
        $mCutoff = (Get-Date).AddDays(-$MirrorRetentionDays)
        $mPruned = 0
        Get-ChildItem -Path $MirrorDir -Filter "${PgDb}_*.dump" -File |
            Where-Object { $_.LastWriteTime -lt $mCutoff } |
            ForEach-Object {
                Write-Host "    Removing (mirror): $($_.Name)"
                Remove-Item $_.FullName -Force
                $mPruned++
            }
        if ($mPruned -eq 0) {
            Write-Host "    Nothing to prune in mirror."
        } else {
            Write-OK "Pruned $mPruned old dump(s) from mirror."
        }
    } else {
        Write-Host "    Mirror retention cleanup skipped (MirrorMaxBackups=0, MirrorRetentionDays=0)."
    }
}

# ---------------------------------------------------------------------------
# Retention cleanup
# ---------------------------------------------------------------------------

if ($MaxBackups -gt 0) {
    Write-Step "Pruning dumps (keep newest $MaxBackups)..."
    $pruned = Invoke-PruneDumpBackupsByCount -Dir $BackupDir -Filter "${PgDb}_*.dump" -MaxBackups $MaxBackups
    if ($pruned -eq 0) {
        Write-Host "    Nothing to prune."
    } else {
        Write-OK "Pruned $pruned old dump(s)."
    }
} elseif ($RetentionDays -gt 0) {
    Write-Step "Pruning dumps older than $RetentionDays days..."
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    $pruned = 0
    Get-ChildItem -Path $BackupDir -Filter "${PgDb}_*.dump" |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        ForEach-Object {
            Write-Host "    Removing: $($_.Name)"
            Remove-Item $_.FullName -Force
            $pruned++
        }
    if ($pruned -eq 0) {
        Write-Host "    Nothing to prune."
    } else {
        Write-OK "Pruned $pruned old dump(s)."
    }
} else {
    Write-Host "    Retention cleanup skipped (MaxBackups=0, RetentionDays=0)."
}

Write-OK "Backup finished successfully."
