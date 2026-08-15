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

$pyArgs = @("python", "tests/test_model_sources.py")
if ($TestKaggle) { $pyArgs += "--test-kaggle" }
if ($SkipDownload) { $pyArgs += "--skip-download" }
if ($Verbose) { $pyArgs += "--verbose" }

Write-Host "Using image-scoring-gpu-shell..." -ForegroundColor Green
Write-Host ""
& "$PSScriptRoot\Invoke-GpuShell.ps1" @pyArgs

Write-Host ""
Read-Host "Press Enter to exit"
