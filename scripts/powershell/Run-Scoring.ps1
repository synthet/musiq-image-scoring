<#
.SYNOPSIS
    Universal Vexlum scoring runner
    Accepts a File or a Folder.
    - If Folder: Runs batch processing (gpu-shell) + Gallery Generation.
    - If File: Runs single image scoring (gpu-shell).

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

if ($IsFolder) {
    Write-Host "FOLDER detected: $ResolvedPath"
    Write-Host "Starting batch processing in image-scoring-gpu-shell..."
    Write-Host ""

    & "$PSScriptRoot\Invoke-GpuShell.ps1" python scripts/python/batch_process_images.py --input-dir $ResolvedPath --output-dir $ResolvedPath --skip-existing
    
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
    Write-Host "Scoring single image in image-scoring-gpu-shell..."
    Write-Host ""

    & "$PSScriptRoot\Invoke-GpuShell.ps1" python scripts/python/run_all_musiq_models.py --image $ResolvedPath
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Scoring Complete."
        Write-Host "JSON result saved next to image."
    }
}

Write-Host ""
Write-Host "Done."
