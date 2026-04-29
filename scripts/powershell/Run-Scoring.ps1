<#
.SYNOPSIS
    Universal Vexlum scoring runner
    Accepts a File or a Folder.
    - If Folder: Runs batch processing (WSL) + Gallery Generation.
    - If File: Runs single image scoring (WSL).

.PARAMETER InputPath
    The path to the file or folder to process.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath
)

# 0. Clean Input Path
# Remove surrounding quotes if passed incorrectly
$InputPath = $InputPath -replace "^['\""]", "" -replace "['\""]$", ""

# 1. Path Handling
try {
    $FullPath = Resolve-Path $InputPath -ErrorAction Stop
}
catch {
    Write-Error "Path not found: $InputPath"
    exit 1
}

$ResolvedPath = $FullPath.Path
$IsFolder = Test-Path $ResolvedPath -PathType Container

# 2. Convert to WSL Path
# E.g. D:\Photos -> /mnt/d/Photos
if ($ResolvedPath -match "^([a-zA-Z]):\\(.*)") {
    $drive = $matches[1].ToLower()
    $rest = $matches[2] -replace "\\", "/"
    $WslPath = "/mnt/$drive/$rest"
}
else {
    Write-Error "Could not convert path to WSL format: $ResolvedPath"
    exit 1
}

# 3. Define Project Paths (Dynamic Detection)
# Get project root from script location (scripts/powershell -> project root)
$ProjectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
# Convert to WSL path format
$WSL_PROJECT_DIR = $ProjectRoot -replace '\\', '/' -replace '^([A-Za-z]):', '/mnt/$1'
$WSL_PROJECT_DIR = $WSL_PROJECT_DIR.ToLower()
# Use simple string interpolation. The && is safe inside the double quotes.
$WSL_PYTHON_CMD = "source ~/.venvs/tf/bin/activate && cd $WSL_PROJECT_DIR"

if ($IsFolder) {
    Write-Host "FOLDER detected: $ResolvedPath"
    Write-Host "Starting Batch Processing in WSL..."
    Write-Host ""
    
    # Simple interpolation. We use single quotes for the inner arguments.
    $cmd = "$WSL_PYTHON_CMD && python scripts/python/batch_process_images.py --input-dir '$WslPath' --output-dir '$WslPath' --skip-existing"
    
    wsl bash -c $cmd
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "Generating Gallery (Local)..."
        
        # Run Gallery Generator locally
        python scripts/python/gallery_generator.py "$ResolvedPath"
        
        $GalleryFile = Join-Path $ResolvedPath "gallery.html"
        if (Test-Path $GalleryFile) {
            Write-Host "Gallery created: $GalleryFile"
            Start-Process $GalleryFile
        }
    }
}
else {
    Write-Host "FILE detected: $ResolvedPath"
    Write-Host "Scoring Single Image in WSL..."
    Write-Host ""
    
    # Simple interpolation.
    $cmd = "$WSL_PYTHON_CMD && python scripts/python/run_all_musiq_models.py --image '$WslPath'"
    
    wsl bash -c $cmd
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Scoring Complete."
        Write-Host "JSON result saved next to image."
    }
}

Write-Host ""
Write-Host "Done."
