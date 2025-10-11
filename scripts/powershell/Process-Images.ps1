# MUSIQ Image Quality Processor
# Usage: .\Process-Images.ps1 "C:\Path\To\Your\Images"

param(
    [Parameter(Mandatory=$true)]
    [string]$InputFolder
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    MUSIQ Image Quality Processor" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Input folder: $InputFolder" -ForegroundColor Yellow
Write-Host ""

# Check if input folder exists
if (-not (Test-Path $InputFolder)) {
    Write-Host "ERROR: Folder does not exist: $InputFolder" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Processing images in: $InputFolder" -ForegroundColor Green
Write-Host "This will run all MUSIQ models (SPAQ, AVA, KONIQ, PAQ2PIQ) on each image." -ForegroundColor Yellow
Write-Host "This may take a while depending on the number of images..." -ForegroundColor Yellow
Write-Host ""

# Check if we're in WSL environment or Windows
try {
    $wslCheck = Get-Command wsl -ErrorAction Stop
    Write-Host "Using WSL environment for MUSIQ processing..." -ForegroundColor Green
    Write-Host ""
    
    # Convert Windows path to WSL path
    $wslPath = $InputFolder -replace '^([A-Z]):', '/mnt/$($matches[1].ToLower())' -replace '\\', '/'
    
    # Run batch processing in WSL
    wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python scripts/python/batch_process_images.py --input-dir '$wslPath' --output-dir '$wslPath'"
} catch {
    Write-Host "Using Windows Python environment for MUSIQ processing..." -ForegroundColor Green
    Write-Host ""
    
    # Run batch processing in Windows
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    python "$PSScriptRoot\..\..\scripts\python\batch_process_images.py" --input-dir $InputFolder --output-dir $InputFolder
}

Write-Host ""
Write-Host "Processing complete!" -ForegroundColor Green
Write-Host "JSON files with quality scores have been generated in: $InputFolder" -ForegroundColor Yellow
Write-Host ""
Write-Host "You can now use create_gallery.bat or Create-Gallery.ps1 to generate an HTML gallery from these results." -ForegroundColor Cyan
Write-Host ""

Read-Host "Press Enter to exit"
