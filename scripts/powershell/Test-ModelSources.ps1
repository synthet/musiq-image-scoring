# Model Sources Test Script - PowerShell Version
# Tests all TensorFlow Hub and Kaggle Hub model sources

param(
    [switch]$TestKaggle,
    [switch]$SkipDownload,
    [switch]$Verbose
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Model Sources Test Script" -ForegroundColor Cyan
Write-Host "   TensorFlow Hub + Kaggle Hub" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Build arguments
$args = @()
if ($TestKaggle) {
    $args += "--test-kaggle"
}
if ($SkipDownload) {
    $args += "--skip-download"
}
if ($Verbose) {
    $args += "--verbose"
}

# Check if we're in WSL environment or Windows
try {
    $wslCheck = Get-Command wsl -ErrorAction Stop
    Write-Host "Using WSL environment for testing..." -ForegroundColor Green
    Write-Host ""
    
    # Run test in WSL with TensorFlow virtual environment
    $argsString = $args -join " "
    wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python tests/test_model_sources.py $argsString"
} catch {
    Write-Host "Using Windows Python environment for testing..." -ForegroundColor Yellow
    Write-Host "Warning: TensorFlow may not be properly configured in Windows." -ForegroundColor Yellow
    Write-Host "WSL is recommended for accurate testing." -ForegroundColor Yellow
    Write-Host ""
    
    # Run test with Windows Python
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    python "$PSScriptRoot\..\..\tests\test_model_sources.py" @args
}

Write-Host ""
Read-Host "Press Enter to exit"

