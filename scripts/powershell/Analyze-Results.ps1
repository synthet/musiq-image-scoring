# Analyze JSON results from MUSIQ batch processing
# Finds best and worst images overall and by each model

param(
    [string]$Directory = "D:\Projects\image-scoring",
    [string]$OutputFile = ""
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   MUSIQ Results Analyzer" -ForegroundColor Cyan
Write-Host "   Finding best and worst images" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if directory exists
if (-not (Test-Path $Directory)) {
    Write-Host "ERROR: Directory not found: $Directory" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Analyzing directory: $Directory" -ForegroundColor Green
Write-Host ""

# Convert Windows path to WSL path
$WslDirectory = $Directory -replace '^D:', '/mnt/d' -replace '\\', '/'

# Build command
$Command = "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python analyze_json_results.py --directory '$WslDirectory'"

if (-not [string]::IsNullOrEmpty($OutputFile)) {
    $Command += " --output '$OutputFile'"
}

try {
    Write-Host "Running analysis..." -ForegroundColor Yellow
    Write-Host "Command: wsl bash -c `"$Command`"" -ForegroundColor Gray
    Write-Host ""
    
    # Execute command
    wsl bash -c $Command
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Analysis complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Check the generated analysis_summary_*.json file for detailed results." -ForegroundColor Cyan
    
    # Find the latest analysis summary file
    $SummaryFiles = Get-ChildItem -Path $Directory -Filter "analysis_summary_*.json" | Sort-Object LastWriteTime -Descending
    if ($SummaryFiles.Count -gt 0) {
        $LatestSummary = $SummaryFiles[0]
        Write-Host "Latest summary: $($LatestSummary.Name)" -ForegroundColor Green
    }
}
catch {
    Write-Host "ERROR: Failed to run analysis: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to exit"
