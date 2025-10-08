# MUSIQ GPU Runner for Windows 11 + WSL2 (PowerShell)
# This script runs MUSIQ with GPU acceleration through WSL2 Ubuntu

param(
    [Parameter(Position=0)]
    [string]$ImagePath,
    
    [Parameter()]
    [string]$FolderPath,
    
    [Parameter()]
    [switch]$TestGPU,
    
    [Parameter()]
    [switch]$Help
)

function Show-Header {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "    MUSIQ GPU Runner (PowerShell)" -ForegroundColor Yellow
    Write-Host "    WSL2 + Ubuntu + TensorFlow GPU" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Show-Help {
    Write-Host "MUSIQ GPU Runner Help" -ForegroundColor Green
    Write-Host "====================" -ForegroundColor Green
    Write-Host ""
    Write-Host "This script runs MUSIQ image quality assessment with GPU acceleration"
    Write-Host "through WSL2 + Ubuntu + TensorFlow."
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  .\Run-MUSIQ-GPU.ps1 -ImagePath `"C:\path\to\image.jpg`""
    Write-Host "  .\Run-MUSIQ-GPU.ps1 -FolderPath `"C:\path\to\images\`""
    Write-Host "  .\Run-MUSIQ-GPU.ps1 -TestGPU"
    Write-Host "  .\Run-MUSIQ-GPU.ps1 -Help"
    Write-Host ""
    Write-Host "Parameters:"
    Write-Host "  -ImagePath    Path to a single image file"
    Write-Host "  -FolderPath   Path to folder containing images"
    Write-Host "  -TestGPU      Test GPU setup and TensorFlow"
    Write-Host "  -Help         Show this help message"
    Write-Host ""
    Write-Host "Supported image formats: JPG, JPEG, PNG, BMP, TIFF"
    Write-Host ""
    Write-Host "Performance:"
    Write-Host "  - GPU: ~5ms per image"
    Write-Host "  - CPU fallback: ~30ms per image"
    Write-Host ""
}

function Test-WSL {
    try {
        $null = wsl --status 2>$null
        return $true
    }
    catch {
        return $false
    }
}

function ConvertTo-WSLPath {
    param([string]$WindowsPath)
    
    $wslPath = $WindowsPath
    $wslPath = $wslPath -replace '^C:\\', '/mnt/c/'
    $wslPath = $wslPath -replace '^D:\\', '/mnt/d/'
    $wslPath = $wslPath -replace '^E:\\', '/mnt/e/'
    $wslPath = $wslPath -replace '^F:\\', '/mnt/f/'
    $wslPath = $wslPath -replace '^G:\\', '/mnt/g/'
    $wslPath = $wslPath -replace '^H:\\', '/mnt/h/'
    $wslPath = $wslPath -replace '\\', '/'
    
    return $wslPath
}

function Test-GPUSetup {
    Write-Host "Testing GPU setup..." -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    
    try {
        $result = wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python test_tf_gpu.py"
        Write-Host $result
    }
    catch {
        Write-Host "ERROR: Failed to test GPU setup" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
    }
    
    Write-Host ""
}

function Process-SingleImage {
    param([string]$Path)
    
    if (-not (Test-Path $Path)) {
        Write-Host "ERROR: File not found: $Path" -ForegroundColor Red
        return
    }
    
    $wslPath = ConvertTo-WSLPath $Path
    
    Write-Host "Processing single image..." -ForegroundColor Yellow
    Write-Host "Input: $Path" -ForegroundColor White
    Write-Host "WSL path: $wslPath" -ForegroundColor Gray
    Write-Host ""
    
    Write-Host "Starting MUSIQ GPU inference..." -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    
    try {
        $result = wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python run_musiq_gpu.py --image '$wslPath'"
        Write-Host $result
    }
    catch {
        Write-Host "ERROR: Failed to process image" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
    }
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Single image processing completed!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Process-MultipleImages {
    param([string]$Path)
    
    if (-not (Test-Path $Path)) {
        Write-Host "ERROR: Folder not found: $Path" -ForegroundColor Red
        return
    }
    
    $wslPath = ConvertTo-WSLPath $Path
    
    Write-Host "Processing multiple images..." -ForegroundColor Yellow
    Write-Host "Input folder: $Path" -ForegroundColor White
    Write-Host "WSL path: $wslPath" -ForegroundColor Gray
    Write-Host ""
    
    Write-Host "Starting batch MUSIQ GPU inference..." -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    
    try {
        $result = wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && for img in '$wslPath'/*.{jpg,jpeg,png,bmp,tiff}; do if [ -f \"`$img\" ]; then echo \"Processing: `$img\"; python run_musiq_gpu.py --image \"`$img\"; echo; fi; done"
        Write-Host $result
    }
    catch {
        Write-Host "ERROR: Failed to process images" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
    }
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Batch processing completed!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
}

# Main execution
Show-Header

# Check if WSL is available
if (-not (Test-WSL)) {
    Write-Host "ERROR: WSL is not installed or not working" -ForegroundColor Red
    Write-Host "Please install WSL2 with Ubuntu first" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Handle parameters
if ($Help) {
    Show-Help
    exit 0
}

if ($TestGPU) {
    Test-GPUSetup
    Read-Host "Press Enter to exit"
    exit 0
}

if ($ImagePath) {
    Process-SingleImage $ImagePath
    Read-Host "Press Enter to exit"
    exit 0
}

if ($FolderPath) {
    Process-MultipleImages $FolderPath
    Read-Host "Press Enter to exit"
    exit 0
}

# Interactive mode
Write-Host "Choose an option:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Process single image" -ForegroundColor White
Write-Host "2. Process multiple images" -ForegroundColor White
Write-Host "3. Test GPU setup" -ForegroundColor White
Write-Host "4. Show help" -ForegroundColor White
Write-Host "5. Exit" -ForegroundColor White
Write-Host ""

$choice = Read-Host "Enter your choice (1-5)"

switch ($choice) {
    "1" {
        $imagePath = Read-Host "Enter path to image file"
        if ($imagePath) {
            Process-SingleImage $imagePath
        }
    }
    "2" {
        $folderPath = Read-Host "Enter path to folder containing images"
        if ($folderPath) {
            Process-MultipleImages $folderPath
        }
    }
    "3" {
        Test-GPUSetup
    }
    "4" {
        Show-Help
    }
    "5" {
        Write-Host "Goodbye!" -ForegroundColor Green
        exit 0
    }
    default {
        Write-Host "Invalid choice. Please try again." -ForegroundColor Red
    }
}

Read-Host "Press Enter to exit"
