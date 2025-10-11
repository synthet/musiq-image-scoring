# Batch process all images in D:\Photos\Export\2025 with comprehensive logging
# All output (including errors and warnings) will be redirected to a log file

param(
    [string]$InputDir = "D:\Photos\Export\2025",
    [string]$OutputDir = "D:\Photos\Export\2025",  # Default: same as input directory
    [string]$LogFile = ""
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   MUSIQ Batch Image Processor" -ForegroundColor Cyan
Write-Host "   Processing all images in directory" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if input directory exists
if (-not (Test-Path $InputDir)) {
    Write-Host "ERROR: Input directory not found: $InputDir" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Generate log file name with current date and time if not provided
if ([string]::IsNullOrEmpty($LogFile)) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $LogFile = "musiq_batch_log_$timestamp.log"
}

Write-Host "Input directory: $InputDir" -ForegroundColor Green
Write-Host "Output directory: $OutputDir" -ForegroundColor Green
Write-Host "Log file: $LogFile" -ForegroundColor Green
Write-Host ""

Write-Host "Starting batch processing..." -ForegroundColor Yellow
Write-Host "All output will be logged to: $LogFile" -ForegroundColor Yellow
Write-Host ""

# Convert Windows paths to WSL paths
$WslInputDir = $InputDir -replace '^D:', '/mnt/d' -replace '\\', '/'
$WslOutputDir = $OutputDir -replace '^D:', '/mnt/d' -replace '\\', '/'

# Run the batch processor through WSL2 and redirect all output to log file
$Command = "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python scripts/python/batch_process_images.py --input-dir '$WslInputDir' --output-dir '$WslOutputDir' --log-file '$LogFile'"

try {
    Write-Host "Executing batch processing command..." -ForegroundColor Cyan
    Write-Host "Command: wsl bash -c `"$Command`"" -ForegroundColor Gray
    
    # Execute command and redirect all output to log file
    wsl bash -c $Command *> $LogFile
    
    # Check if the log file was created
    if (Test-Path $LogFile) {
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Green
        Write-Host "Batch processing completed!" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Log file created: $LogFile" -ForegroundColor Green
        Write-Host ""
        
        # Show the last few lines of the log
        Write-Host "Last few lines of the log:" -ForegroundColor Yellow
        Write-Host "----------------------------------------" -ForegroundColor Gray
        
        try {
            $logContent = Get-Content $LogFile -Tail 10
            $logContent | ForEach-Object { Write-Host $_ -ForegroundColor White }
        }
        catch {
            Write-Host "Could not read log file content" -ForegroundColor Red
        }
        
        Write-Host "----------------------------------------" -ForegroundColor Gray
        Write-Host ""
        Write-Host "To view the full log, open: $LogFile" -ForegroundColor Cyan
        
        # Check if batch summary was created
        $summaryFiles = Get-ChildItem -Path $OutputDir -Filter "batch_summary_*.json" | Sort-Object LastWriteTime -Descending
        if ($summaryFiles.Count -gt 0) {
            $latestSummary = $summaryFiles[0]
            Write-Host "Batch summary created: $($latestSummary.FullName)" -ForegroundColor Green
        }
    }
    else {
        Write-Host "ERROR: Log file was not created. Check for errors." -ForegroundColor Red
    }
}
catch {
    Write-Host "ERROR: Failed to execute batch processing: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Check the log file for more details: $LogFile" -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Press Enter to exit"
