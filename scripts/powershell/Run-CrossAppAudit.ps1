# Run a lightweight cross-app audit for the sibling `image-scoring` and
# `electron-image-scoring` repos. This is an audit helper, not an E2E harness.
#
# Example:
#   .\scripts\powershell\Run-CrossAppAudit.ps1

param(
    [string]$BackendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$ElectronRoot = (Join-Path (Split-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path -Parent) "electron-image-scoring"),
    [string]$BackendApiBaseUrl = "http://127.0.0.1:7860/api",
    [int]$HttpTimeoutSec = 10,
    [int]$RetryCount = 3,
    [int]$RetryDelaySec = 2,
    [int]$JobPollAttempts = 5,
    [int]$JobPollIntervalSec = 2,
    [switch]$SmokeBlocking,
    [string]$SummaryJsonPath = ""
)

$EXIT_SUCCESS = 0
$EXIT_REQUIRED_FAILURE = 10
$EXIT_REQUIRED_BLOCKED = 11
$EXIT_UNEXPECTED_ERROR = 12

function Add-AuditResult {
    param(
        [System.Collections.Generic.List[object]]$Results,
        [string]$Name,
        [string]$Status,
        [int]$ExitCode,
        [bool]$Required = $true,
        [string]$Notes = ""
    )

    $Results.Add([pscustomobject]@{
        Name = $Name
        Status = $Status
        ExitCode = $ExitCode
        Required = $Required
        Notes = $Notes
    })
}

function Invoke-WithRetry {
    param(
        [scriptblock]$Operation,
        [string]$OperationName,
        [int]$MaxAttempts = 3,
        [int]$DelaySec = 2
    )

    $attempt = 0
    while ($attempt -lt $MaxAttempts) {
        $attempt += 1
        try {
            return & $Operation
        } catch {
            if ($attempt -ge $MaxAttempts) {
                throw "[$OperationName] failed after $attempt attempts. Last error: $($_.Exception.Message)"
            }
            Start-Sleep -Seconds $DelaySec
        }
    }
}

function Invoke-BackendSmokeCheck {
    param(
        [string]$ApiBaseUrl,
        [string]$RepoRoot,
        [int]$TimeoutSec,
        [int]$MaxRetries,
        [int]$RetryBackoffSec,
        [int]$PollAttempts,
        [int]$PollIntervalSec
    )

    $runId = $null
    $healthResponse = Invoke-WithRetry -OperationName "GET $ApiBaseUrl/health" -MaxAttempts $MaxRetries -DelaySec $RetryBackoffSec -Operation {
        Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/health" -TimeoutSec $TimeoutSec
    }
    if (-not $healthResponse -or $healthResponse.status -ne "healthy") {
        throw "Health check failed. Expected status='healthy' but got '$($healthResponse.status)'."
    }

    $smokeScope = Join-Path $RepoRoot ".tmp\cross-app-audit-smoke"
    New-Item -ItemType Directory -Path $smokeScope -Force | Out-Null
    $submitPayload = @{
        scope_type = "folder"
        scope_paths = @($smokeScope)
        stages = @("indexing")
        run_mode = "process_unprocessed_or_empty"
    }
    $submitBody = $submitPayload | ConvertTo-Json -Depth 6
    $submitResponse = Invoke-WithRetry -OperationName "POST $ApiBaseUrl/runs/submit" -MaxAttempts $MaxRetries -DelaySec $RetryBackoffSec -Operation {
        Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/runs/submit" -ContentType "application/json" -Body $submitBody -TimeoutSec $TimeoutSec
    }
    if (-not $submitResponse.success -or -not $submitResponse.run_id) {
        throw "Run submission failed or run_id was missing. Response: $($submitResponse | ConvertTo-Json -Depth 6 -Compress)"
    }
    $runId = [int]$submitResponse.run_id

    $observedStatuses = New-Object System.Collections.Generic.List[string]
    $statusCheckPassed = $false
    for ($i = 1; $i -le $PollAttempts; $i++) {
        $job = Invoke-WithRetry -OperationName "GET $ApiBaseUrl/jobs/$runId (poll $i/$PollAttempts)" -MaxAttempts $MaxRetries -DelaySec $RetryBackoffSec -Operation {
            Invoke-RestMethod -Method Get -Uri "$ApiBaseUrl/jobs/$runId" -TimeoutSec $TimeoutSec
        }
        $status = [string]($job.status)
        if (-not [string]::IsNullOrWhiteSpace($status)) {
            $observedStatuses.Add($status)
        }
        $hasPhaseData = ($job.phases -is [System.Array] -and $job.phases.Count -gt 0)
        if ($hasPhaseData -or $observedStatuses.Count -ge 2) {
            $statusCheckPassed = $true
            break
        }
        Start-Sleep -Seconds $PollIntervalSec
    }
    if (-not $statusCheckPassed) {
        throw "Follow-up status assertion failed for run_id=$runId. Observed statuses: $($observedStatuses -join ', ')."
    }

    return @{
        run_id = $runId
        queue_position = $submitResponse.queue_position
        observed_statuses = @($observedStatuses)
    }
}

function Get-BackendPytestBlocker {
    param([string]$RepoRoot)

    $venvCfg = Join-Path $RepoRoot ".venv\pyvenv.cfg"
    if (-not (Test-Path $venvCfg)) {
        return $null
    }

    $content = Get-Content $venvCfg -Raw
    if ($content -match "WindowsApps\\PythonSoftwareFoundation") {
        return "Local .venv points at the Windows Store Python shim; skip backend pytest until the venv is rebuilt against a real Python install."
    }

    return $null
}

if (-not (Test-Path $BackendRoot)) {
    throw "Backend root not found: $BackendRoot"
}

if (-not (Test-Path $ElectronRoot)) {
    throw "Electron root not found: $ElectronRoot"
}

try {
    $results = New-Object System.Collections.Generic.List[object]

    Write-Host "Backend root:  $BackendRoot"
    Write-Host "Electron root: $ElectronRoot"
    Write-Host "Backend API:   $BackendApiBaseUrl"
    Write-Host ""

    Push-Location $ElectronRoot
    try {
        Write-Host ""
        Write-Host "[RUN] node scripts/validate-api-types.mjs"
        & node scripts/validate-api-types.mjs
        Add-AuditResult -Results $results -Name "Electron contract validator" -Status ($(if ($LASTEXITCODE -eq 0) { "PASS" } else { "FAIL" })) -ExitCode $LASTEXITCODE

        Write-Host ""
        Write-Host "[RUN] cmd /d /s /c `"npm run test:run -- electron/apiUrlResolver.test.ts src/services/WebSocketService.test.ts`""
        & cmd /d /s /c "npm run test:run -- electron/apiUrlResolver.test.ts src/services/WebSocketService.test.ts"
        Add-AuditResult -Results $results -Name "Electron resolver + WebSocket tests" -Status ($(if ($LASTEXITCODE -eq 0) { "PASS" } else { "FAIL" })) -ExitCode $LASTEXITCODE
    } finally {
        Pop-Location
    }

    $backendBlocker = Get-BackendPytestBlocker -RepoRoot $BackendRoot
    if ($backendBlocker) {
        Write-Host ""
        Write-Host "[BLOCKED] Backend API + events pytest"
        Write-Host $backendBlocker
        Add-AuditResult -Results $results -Name "Backend API + events pytest" -Status "BLOCKED" -ExitCode 1 -Notes $backendBlocker
    } else {
        Push-Location $BackendRoot
        try {
            Write-Host ""
            Write-Host "[RUN] .\.venv\Scripts\pytest.exe tests/test_api_queue.py tests/test_events.py -q"
            & .\.venv\Scripts\pytest.exe tests/test_api_queue.py tests/test_events.py -q
            Add-AuditResult -Results $results -Name "Backend API + events pytest" -Status ($(if ($LASTEXITCODE -eq 0) { "PASS" } else { "FAIL" })) -ExitCode $LASTEXITCODE
        } finally {
            Pop-Location
        }
    }

    Write-Host ""
    Write-Host "[RUN] Backend API smoke (health + submit + status progression)"
    try {
        $smokeInfo = Invoke-BackendSmokeCheck -ApiBaseUrl $BackendApiBaseUrl -RepoRoot $BackendRoot -TimeoutSec $HttpTimeoutSec -MaxRetries $RetryCount -RetryBackoffSec $RetryDelaySec -PollAttempts $JobPollAttempts -PollIntervalSec $JobPollIntervalSec
        $smokeNotes = "run_id=$($smokeInfo.run_id); queue_position=$($smokeInfo.queue_position); statuses=$([string]::Join(',', $smokeInfo.observed_statuses))"
        Add-AuditResult -Results $results -Name "Backend API smoke" -Status "PASS" -ExitCode 0 -Required $SmokeBlocking.IsPresent -Notes $smokeNotes
    } catch {
        $smokeStatus = if ($SmokeBlocking.IsPresent) { "FAIL" } else { "WARN" }
        $smokeExit = if ($SmokeBlocking.IsPresent) { 1 } else { 0 }
        Add-AuditResult -Results $results -Name "Backend API smoke" -Status $smokeStatus -ExitCode $smokeExit -Required $SmokeBlocking.IsPresent -Notes $_.Exception.Message
    }

    Write-Host ""
    Write-Host "Summary"
    Write-Host "-------"
    $results | Select-Object Name, Status, ExitCode, Required, Notes | Format-Table -Wrap -AutoSize

    $requiredResults = @($results | Where-Object { $_.Required })
    $finalExitCode = $EXIT_SUCCESS
    if ($requiredResults.Status -contains "BLOCKED") {
        $finalExitCode = $EXIT_REQUIRED_BLOCKED
    } elseif ($requiredResults.Status -contains "FAIL") {
        $finalExitCode = $EXIT_REQUIRED_FAILURE
    }

    $summary = [pscustomobject]@{
        backend_root = $BackendRoot
        electron_root = $ElectronRoot
        backend_api_base_url = $BackendApiBaseUrl
        smoke_blocking = $SmokeBlocking.IsPresent
        retry_count = $RetryCount
        retry_delay_sec = $RetryDelaySec
        http_timeout_sec = $HttpTimeoutSec
        job_poll_attempts = $JobPollAttempts
        job_poll_interval_sec = $JobPollIntervalSec
        final_exit_code = $finalExitCode
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        results = @($results)
    }

    $summaryJson = $summary | ConvertTo-Json -Depth 8 -Compress
    Write-Host "AUDIT_SUMMARY_JSON=$summaryJson"

    if (-not [string]::IsNullOrWhiteSpace($SummaryJsonPath)) {
        $summaryDir = Split-Path -Parent $SummaryJsonPath
        if ($summaryDir -and -not (Test-Path $summaryDir)) {
            New-Item -ItemType Directory -Path $summaryDir -Force | Out-Null
        }
        $summary | ConvertTo-Json -Depth 8 | Set-Content -Path $SummaryJsonPath
        Write-Host "Summary JSON written to: $SummaryJsonPath"
    }

    exit $finalExitCode
} catch {
    Write-Error $_
    exit $EXIT_UNEXPECTED_ERROR
}
