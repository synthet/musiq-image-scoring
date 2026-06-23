<#
.SYNOPSIS
    Safely restores a custom-format pg_dump into a PostgreSQL database.

.DESCRIPTION
    The sanctioned counterpart to Backup-Postgres.ps1. Designed to make an
    accidental "wrong dump / wrong target" restore impossible to do silently:

      1. ALWAYS takes a fresh *_pre-restore.dump of the CURRENT target DB first,
         so any mistake is recoverable in one step.
      2. Prints the source dump's mtime/size and pg_restore --list header, plus a
         before snapshot (images count + max id) so you see exactly what you are
         about to overwrite.
      3. Gates the destructive pg_restore --clean behind ShouldProcess (-WhatIf to
         preview, -Confirm:$false to run unattended). High ConfirmImpact => it
         prompts by default in an interactive shell.
      4. After restore, realigns SERIAL sequences (postgres_sequence_repair.py) and
         prints a before/after diff, WARNING LOUDLY if the row count dropped.

    Docker-first (docker exec into -Container), mirroring Backup-Postgres.ps1.
    The 2026-06 regression (an old dump restored over live; sequence rewound
    198499 -> 190180) is exactly what step 1 + step 4 are here to prevent/catch.

.PARAMETER DumpFile
    Path to the custom-format .dump to restore (required).

.PARAMETER TargetDb
    Database to restore INTO. Defaults to the dbname from merged config.

.PARAMETER Container
    Docker container running the target Postgres. Default: image-scoring-postgres.
    For the e2e instance use: image-scoring-postgres-e2e.

.PARAMETER PgPort
    HOST-side mapped port, used by the sequence-repair step and host psql checks.
    Defaults to the port from merged config (live = 5432; e2e = 5433).

.PARAMETER SafetyBackupDir
    Where the pre-restore safety dump is written. Default: <root>\backups\postgres.

.PARAMETER SkipSequenceRepair
    Skip postgres_sequence_repair.py after restore (not recommended).

.EXAMPLE
    # Preview only -- no changes:
    .\Restore-Postgres.ps1 -DumpFile ..\..\backups\postgres\image_scoring_20260621_005634.dump -WhatIf

.EXAMPLE
    # Restore into the e2e container unattended (verification path, port 5433):
    .\Restore-Postgres.ps1 -DumpFile ..\..\backups\postgres\image_scoring_20260621_005634.dump `
        -Container image-scoring-postgres-e2e -TargetDb image_scoring_test -PgPort 5433 -Confirm:$false
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory = $true)]
    [string]$DumpFile,
    [string]$ConfigPath      = $null,
    [string]$TargetDb        = $null,
    [string]$Container       = "image-scoring-postgres",
    [int]   $PgPort          = 0,
    [string]$PgUser          = $null,
    [string]$PgPassword      = $null,
    [string]$SafetyBackupDir = $null,
    [switch]$SkipSequenceRepair
)

if ([string]::IsNullOrEmpty($PSScriptRoot)) {
    $PSScriptRoot = Split-Path -Parent -Path $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrEmpty($ConfigPath)) {
    $ConfigPath = Join-Path $PSScriptRoot "..\..\config.json"
}
if ([string]::IsNullOrEmpty($SafetyBackupDir)) {
    $SafetyBackupDir = Join-Path $PSScriptRoot "..\..\backups\postgres"
}

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step([string]$msg) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $msg" -ForegroundColor Cyan }
function Write-OK([string]$msg)   { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] OK  $msg" -ForegroundColor Green }
function Write-Fail([string]$msg) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ERR $msg" -ForegroundColor Red }
function Write-Warn([string]$msg) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] !!! $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
# Validate the source dump
# ---------------------------------------------------------------------------

if (-not (Test-Path -LiteralPath $DumpFile)) {
    Write-Fail "Dump file not found: $DumpFile"
    exit 1
}
$DumpFile = (Resolve-Path -LiteralPath $DumpFile).Path
$dumpItem = Get-Item -LiteralPath $DumpFile
if ($dumpItem.Length -eq 0) {
    Write-Fail "Dump file is empty: $DumpFile"
    exit 1
}
$dumpMB = [math]::Round($dumpItem.Length / 1MB, 2)

# ---------------------------------------------------------------------------
# Load connection config (config.json merged with environment.json via Python)
# ---------------------------------------------------------------------------

$ConfigPath  = (Resolve-Path $ConfigPath).Path
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
if ([string]::IsNullOrEmpty($TargetDb))   { $TargetDb   = if ($pgCfg.dbname)   { $pgCfg.dbname }   else { "image_scoring" } }
if ([string]::IsNullOrEmpty($PgUser))     { $PgUser     = if ($pgCfg.user)     { $pgCfg.user }     else { "postgres" } }
if ([string]::IsNullOrEmpty($PgPassword)) { $PgPassword = if ($pgCfg.password) { $pgCfg.password } else { "postgres" } }
if ($PgPort -le 0)                        { $PgPort     = if ($pgCfg.port)     { [int]$pgCfg.port } else { 5432 } }

# ---------------------------------------------------------------------------
# Preconditions: docker + container running
# ---------------------------------------------------------------------------

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Fail "docker is not available on PATH. This wrapper restores via docker exec."
    exit 1
}
$containerState = docker inspect --format "{{.State.Status}}" $Container 2>&1
if ($containerState -ne "running") {
    Write-Fail "Container '$Container' is not running (state: $containerState)."
    exit 1
}

# In-container psql helper: always connects to the container's own postgres.
function Invoke-ContainerScalar([string]$sql) {
    $out = docker exec -e PGPASSWORD=$PgPassword $Container psql -U $PgUser -d $TargetDb -tAc $sql 2>&1
    if ($LASTEXITCODE -ne 0) { return $null }
    return ($out | Out-String).Trim()
}

# ---------------------------------------------------------------------------
# Show what we are about to do (source + current target snapshot)
# ---------------------------------------------------------------------------

Write-Step "Restore plan"
Write-Host  "    Source dump : $DumpFile"
Write-Host  "    Dump size   : $dumpMB MB"
Write-Host  "    Dump mtime  : $($dumpItem.LastWriteTime)"
Write-Host  "    Target      : container=$Container  db=$TargetDb  user=$PgUser  (host port=$PgPort)"

Write-Step "Source dump header (pg_restore --list, first lines):"
$dumpInContainer = "/tmp/restore_$([System.IO.Path]::GetFileName($DumpFile))"
docker cp $DumpFile "${Container}:${dumpInContainer}" | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Fail "docker cp of dump into container failed."; exit 1 }
$listOut = docker exec $Container pg_restore --list $dumpInContainer 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "pg_restore --list failed -- is this a valid custom-format dump?"
    docker exec $Container rm -f $dumpInContainer 2>$null | Out-Null
    exit 1
}
($listOut | Select-Object -First 12) | ForEach-Object { Write-Host "    $_" }

# Before snapshot (two simple scalar queries -- avoids '||' which Windows PowerShell 5.1 mis-parses inline)
$beforeImages = $null; $beforeMax = $null
$cnt = Invoke-ContainerScalar "SELECT count(*) FROM images"
if ($cnt -and $cnt -match '^\d+$') {
    $beforeImages = [int64]$cnt
    $mx = Invoke-ContainerScalar "SELECT COALESCE(max(id),0) FROM images"
    if ($mx -and $mx -match '^\d+$') { $beforeMax = [int64]$mx }
}
if ($null -ne $beforeImages) {
    Write-Step "Current target BEFORE restore: images=$beforeImages  max(id)=$beforeMax"
} else {
    Write-Step "Current target BEFORE restore: no 'images' table (fresh/empty DB?)"
}

# ---------------------------------------------------------------------------
# Step 1 -- ALWAYS take a pre-restore safety dump of the current target
# ---------------------------------------------------------------------------

$SafetyBackupDir = [System.IO.Path]::GetFullPath($SafetyBackupDir)
if (-not (Test-Path $SafetyBackupDir)) { New-Item -ItemType Directory -Path $SafetyBackupDir -Force | Out-Null }
$ts        = Get-Date -Format "yyyyMMdd_HHmmss"
$safetyOut = Join-Path $SafetyBackupDir "${TargetDb}_${ts}_pre-restore.dump"

if ($PSCmdlet.ShouldProcess($safetyOut, "pg_dump current '$TargetDb' as pre-restore safety backup")) {
    Write-Step "Taking pre-restore safety dump -> $safetyOut"
    $safetyInContainer = "/tmp/${TargetDb}_${ts}_pre-restore.dump"
    docker exec -e PGPASSWORD=$PgPassword $Container pg_dump -U $PgUser -d $TargetDb --format=custom --no-password --file=$safetyInContainer
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Pre-restore safety dump FAILED. Aborting before any destructive action."
        docker exec $Container rm -f $dumpInContainer 2>$null | Out-Null
        exit 1
    }
    docker cp "${Container}:${safetyInContainer}" $safetyOut | Out-Null
    docker exec $Container rm -f $safetyInContainer 2>$null | Out-Null
    if (-not (Test-Path $safetyOut) -or (Get-Item $safetyOut).Length -eq 0) {
        Write-Fail "Safety dump missing/empty on host. Aborting."
        exit 1
    }
    $sMB = [math]::Round((Get-Item $safetyOut).Length / 1MB, 2)
    Write-OK "Safety dump written ($sMB MB). If this restore is wrong, recover with:"
    Write-Host "    .\Restore-Postgres.ps1 -DumpFile `"$safetyOut`" -Container $Container -TargetDb $TargetDb -PgPort $PgPort" -ForegroundColor DarkGray
} else {
    Write-Warn "Pre-restore safety dump skipped (WhatIf)."
}

# ---------------------------------------------------------------------------
# Step 2 -- destructive restore (gated by ShouldProcess)
# ---------------------------------------------------------------------------

$restoreDesc = "RESTORE '$DumpFile' OVER db '$TargetDb' in container '$Container' (pg_restore --clean --if-exists)"
if ($PSCmdlet.ShouldProcess($TargetDb, $restoreDesc)) {
    Write-Step "Restoring (pg_restore --clean --if-exists --no-owner --no-privileges)..."
    docker exec -e PGPASSWORD=$PgPassword $Container `
        pg_restore --username=$PgUser --dbname=$TargetDb `
        --clean --if-exists --no-owner --no-privileges --no-password `
        $dumpInContainer
    $restoreExit = $LASTEXITCODE
    docker exec $Container rm -f $dumpInContainer 2>$null | Out-Null
    # pg_restore exits non-zero on benign "does not exist" DROPs with --clean; treat
    # only a missing post-restore table as fatal (checked below).
    if ($restoreExit -ne 0) {
        Write-Warn "pg_restore exited $restoreExit (often benign --clean DROP warnings). Verifying result..."
    }

    # ---------------------------------------------------------------------
    # Step 3 -- sequence repair
    # ---------------------------------------------------------------------
    if (-not $SkipSequenceRepair) {
        Write-Step "Repairing SERIAL sequences (postgres_sequence_repair.py)..."
        $repair = Join-Path $ProjectRoot "scripts\python\postgres_sequence_repair.py"
        $env:PGPASSWORD = $PgPassword
        try {
            & python $repair --pg-host 127.0.0.1 --pg-port $PgPort --pg-db $TargetDb --pg-user $PgUser --pg-password $PgPassword
            if ($LASTEXITCODE -ne 0) { Write-Warn "Sequence repair returned $LASTEXITCODE -- run it manually if inserts fail." }
        } finally {
            Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
        }
    }

    # ---------------------------------------------------------------------
    # Step 4 -- after snapshot + row-drop guard
    # ---------------------------------------------------------------------
    $afterImages = $null; $afterMax = $null
    $cnt2 = Invoke-ContainerScalar "SELECT count(*) FROM images"
    if ($cnt2 -and $cnt2 -match '^\d+$') {
        $afterImages = [int64]$cnt2
        $mx2 = Invoke-ContainerScalar "SELECT COALESCE(max(id),0) FROM images"
        if ($mx2 -and $mx2 -match '^\d+$') { $afterMax = [int64]$mx2 }
    }
    if ($null -eq $afterImages) {
        Write-Fail "After restore the 'images' table is unreadable -- restore likely FAILED. Recover from the safety dump above."
        exit 1
    }
    Write-OK "AFTER restore: images=$afterImages  max(id)=$afterMax"
    if ($null -ne $beforeImages) {
        $delta = $afterImages - $beforeImages
        Write-Host "    images delta: $beforeImages -> $afterImages ($([string]::Format('{0:+#;-#;0}', $delta)))"
        if ($afterImages -lt $beforeImages) {
            Write-Warn "ROW COUNT DROPPED by $([math]::Abs($delta)). You restored a SMALLER/OLDER dataset over a larger one."
            Write-Warn "If this was not intended, restore the safety dump shown above to roll back."
        }
        if ($afterMax -lt $beforeMax) {
            Write-Warn "max(images.id) went BACKWARDS ($beforeMax -> $afterMax) -- same signature as the 2026-06 regression."
        }
    }
    Write-OK "Restore finished."
} else {
    Write-Warn "Destructive restore skipped (WhatIf). No changes were made to '$TargetDb'."
    docker exec $Container rm -f $dumpInContainer 2>$null | Out-Null
}
