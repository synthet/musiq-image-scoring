# MUSIQ Multi-Model Drag-and-Drop Runner for Windows 11 + WSL2
# Runs all available MUSIQ models on an image and saves results to JSON
# Simply drag and drop an image file onto this script

param(
    [Parameter(ValueFromPipeline=$true)]
    [string[]]$ImagePaths
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   MUSIQ Multi-Model Drag-and-Drop Runner" -ForegroundColor Cyan
Write-Host "   WSL2 + Ubuntu + TensorFlow GPU" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if any files were provided
if (-not $ImagePaths -or $ImagePaths.Count -eq 0) {
    Write-Host "No files provided. Please drag and drop an image file onto this script." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Supported formats: JPG, JPEG, PNG, BMP, TIFF" -ForegroundColor Green
    Write-Host ""
    Write-Host "This script will run all available MUSIQ models:" -ForegroundColor Green
    Write-Host "  - SPAQ (range: 1-5)" -ForegroundColor Green
    Write-Host "  - AVA (range: 1-10)" -ForegroundColor Green
    Write-Host "  - KONIQ (range: 1-5)" -ForegroundColor Green
    Write-Host "  - PAQ2PIQ (range: 1-5)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Results will be saved as JSON file with same name as image." -ForegroundColor Green
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Process each dropped file
foreach ($ImagePath in $ImagePaths) {
    Write-Host "Processing: $ImagePath" -ForegroundColor Yellow
    
    # Check if file exists
    if (-not (Test-Path $ImagePath)) {
        Write-Host "ERROR: File not found: $ImagePath" -ForegroundColor Red
        Write-Host ""
        continue
    }
    
    # Check if it's an image file
    $Extension = [System.IO.Path]::GetExtension($ImagePath).ToLower()
    $SupportedExtensions = @('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
    
    if ($Extension -notin $SupportedExtensions) {
        Write-Host "WARNING: $ImagePath may not be a supported image format" -ForegroundColor Yellow
        Write-Host "Supported formats: JPG, JPEG, PNG, BMP, TIFF" -ForegroundColor Green
        Write-Host ""
    }
    
    # Convert Windows path to WSL path
    $WslPath = $ImagePath -replace '^([A-Z]):', '/mnt/$($matches[1].ToLower())' -replace '\\', '/'
    
    Write-Host "WSL path: $WslPath" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "Starting MUSIQ multi-model inference..." -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    
    # Run MUSIQ multi-model through WSL2
    $Command = "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python run_all_musiq_models.py --image '$WslPath' --output-dir /mnt/d/Projects/image-scoring"
    
    try {
        wsl bash -c $Command
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Green
        Write-Host "Processing completed for: $ImagePath" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
    }
    catch {
        Write-Host "ERROR: Failed to process $ImagePath" -ForegroundColor Red
        Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    }
    
    Write-Host ""
}

Write-Host "All files processed!" -ForegroundColor Green
Write-Host ""
Write-Host "JSON results files have been saved in the source folder." -ForegroundColor Green
Write-Host ""
Read-Host "Press Enter to exit"
