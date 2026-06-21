<#
.SYNOPSIS
    Prevent Windows from sleeping (system + display) until stopped.

.DESCRIPTION
    Calls SetThreadExecutionState in a loop. Start launches a hidden detached
    PowerShell worker; Stop ends keep-awake workers; Status lists PIDs.

.PARAMETER Action
    Start | Stop | Status | Worker. Default: Start. Worker is internal.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Keep-Awake.ps1 -Action Start

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Keep-Awake.ps1 -Action Stop
#>
[CmdletBinding()]
param(
    [ValidateSet('Start', 'Stop', 'Status', 'Worker')]
    [string] $Action = 'Start'
)

$ErrorActionPreference = 'Stop'
$ScriptPath = $MyInvocation.MyCommand.Path

function Get-KeepAwakeProcesses {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*Keep-Awake.ps1*" -and $_.CommandLine -like "*-Action Worker*" }
}

function Invoke-KeepAwakeLoop {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class KeepAwake {
    public const uint ES_CONTINUOUS = 0x80000000;
    public const uint ES_SYSTEM_REQUIRED = 0x00000001;
    public const uint ES_DISPLAY_REQUIRED = 0x00000002;

    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);

    public static void PreventSleep() {
        SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED);
    }
}
'@

    while ($true) {
        [KeepAwake]::PreventSleep()
        Start-Sleep -Seconds 30
    }
}

function Start-KeepAwakeWorker {
    $existing = @(Get-KeepAwakeProcesses)
    if ($existing.Count -gt 0) {
        Write-Host "Keep-awake already running (PID $($existing[0].ProcessId))."
        return
    }

    # Start-Process joins ArgumentList into one command line. Preserve quotes
    # around the script path so repositories under paths with spaces work.
    $quotedScriptPath = '"{0}"' -f $ScriptPath
    $args = @(
        '-NoProfile',
        '-WindowStyle', 'Hidden',
        '-ExecutionPolicy', 'Bypass',
        '-File', $quotedScriptPath,
        '-Action', 'Worker'
    )

    # Hidden child process; survives Cursor terminal cleanup.
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $args -WindowStyle Hidden -PassThru
    Write-Host "Keep-awake started (PID $($proc.Id)). Run -Action Stop when sleep is allowed again."
}

function Stop-KeepAwakeWorkers {
    $procs = @(Get-KeepAwakeProcesses)
    if ($procs.Count -eq 0) {
        Write-Host 'Keep-awake is not running.'
        return
    }

    foreach ($p in $procs) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped PID $($p.ProcessId)"
    }
}

function Show-KeepAwakeStatus {
    $procs = @(Get-KeepAwakeProcesses)
    if ($procs.Count -eq 0) {
        Write-Host 'Keep-awake is not running.'
        return
    }

    foreach ($p in $procs) {
        Write-Host "Running PID $($p.ProcessId)"
    }
}

switch ($Action) {
    'Worker' { Invoke-KeepAwakeLoop }
    'Start' { Start-KeepAwakeWorker }
    'Stop' { Stop-KeepAwakeWorkers }
    'Status' { Show-KeepAwakeStatus }
}
