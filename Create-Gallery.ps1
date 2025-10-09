# Wrapper script for backward compatibility
# Calls the actual script in scripts/powershell/

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    $RemainingArgs
)

$ScriptPath = Join-Path $PSScriptRoot "scripts\powershell\Create-Gallery.ps1"
& $ScriptPath @RemainingArgs

