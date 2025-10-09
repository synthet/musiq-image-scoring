@echo off
REM MUSIQ GPU Runner for Windows 11 + WSL2
REM This script runs MUSIQ with GPU acceleration through WSL2 Ubuntu

echo ========================================
echo    MUSIQ GPU Runner (WSL2 + Ubuntu)
echo ========================================
echo.

REM Check if an image path was provided
if "%~1"=="" (
    echo Usage: run_musiq_gpu.bat "path\to\your\image.jpg"
    echo.
    echo Example: run_musiq_gpu.bat "C:\Users\YourName\Pictures\photo.jpg"
    echo Example: run_musiq_gpu.bat "sample.jpg"
    echo.
    pause
    exit /b 1
)

set "IMAGE_PATH=%~1"

REM Check if the image file exists
if not exist "%IMAGE_PATH%" (
    echo ERROR: Image file not found: %IMAGE_PATH%
    echo.
    pause
    exit /b 1
)

echo Input image: %IMAGE_PATH%
echo.

REM Convert Windows path to WSL path
set "WSL_IMAGE_PATH=%IMAGE_PATH%"
set "WSL_IMAGE_PATH=%WSL_IMAGE_PATH:C:\=/mnt/c/%"
set "WSL_IMAGE_PATH=%WSL_IMAGE_PATH:D:\=/mnt/d/%"
set "WSL_IMAGE_PATH=%WSL_IMAGE_PATH:E:\=/mnt/e/%"
set "WSL_IMAGE_PATH=%WSL_IMAGE_PATH:F:\=/mnt/f/%"
set "WSL_IMAGE_PATH=%WSL_IMAGE_PATH:G:\=/mnt/g/%"
set "WSL_IMAGE_PATH=%WSL_IMAGE_PATH:H:\=/mnt/h/%"
set "WSL_IMAGE_PATH=%WSL_IMAGE_PATH:\=/%"

echo Converting to WSL path: %WSL_IMAGE_PATH%
echo.

echo Starting MUSIQ GPU inference...
echo ========================================
echo.

REM Run MUSIQ through WSL2
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python run_musiq_gpu.py --image '%WSL_IMAGE_PATH%'"

echo.
echo ========================================
echo MUSIQ GPU inference completed!
echo ========================================
echo.
pause
