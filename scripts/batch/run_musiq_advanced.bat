@echo off
setlocal enabledelayedexpansion

REM Advanced MUSIQ GPU Runner for Windows 11 + WSL2
REM This script provides multiple options for running MUSIQ with GPU acceleration

echo ========================================
echo    MUSIQ GPU Runner (Advanced)
echo    WSL2 + Ubuntu + TensorFlow GPU
echo ========================================
echo.

REM Check if WSL is available
wsl --status >nul 2>&1
if errorlevel 1 (
    echo ERROR: WSL is not installed or not working
    echo Please install WSL2 with Ubuntu first
    echo.
    pause
    exit /b 1
)

REM Check if arguments were provided
if "%~1"=="" goto :menu

REM Single image mode
set "IMAGE_PATH=%~1"
goto :process_single

:menu
echo Choose an option:
echo.
echo 1. Process single image
echo 2. Process multiple images
echo 3. Test GPU setup
echo 4. Show help
echo 5. Exit
echo.
set /p choice="Enter your choice (1-5): "

if "%choice%"=="1" goto :single_image
if "%choice%"=="2" goto :multiple_images
if "%choice%"=="3" goto :test_gpu
if "%choice%"=="4" goto :show_help
if "%choice%"=="5" goto :exit
echo Invalid choice. Please try again.
echo.
goto :menu

:single_image
echo.
set /p IMAGE_PATH="Enter path to image file: "
if "!IMAGE_PATH!"=="" (
    echo No image path provided.
    goto :menu
)
goto :process_single

:multiple_images
echo.
set /p FOLDER_PATH="Enter path to folder containing images: "
if "!FOLDER_PATH!"=="" (
    echo No folder path provided.
    goto :menu
)
goto :process_multiple

:test_gpu
echo.
echo Testing GPU setup...
echo ========================================
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python test_tf_gpu.py"
echo.
pause
goto :menu

:show_help
echo.
echo MUSIQ GPU Runner Help
echo =====================
echo.
echo This script runs MUSIQ image quality assessment with GPU acceleration
echo through WSL2 + Ubuntu + TensorFlow.
echo.
echo Usage:
echo   run_musiq_advanced.bat "path\to\image.jpg"
echo   run_musiq_advanced.bat
echo.
echo Supported image formats: JPG, JPEG, PNG, BMP, TIFF
echo.
echo GPU Requirements:
echo   - NVIDIA GPU with CUDA support
echo   - WSL2 with Ubuntu installed
echo   - TensorFlow GPU environment set up
echo.
echo Performance:
echo   - GPU: ~5ms per image
echo   - CPU fallback: ~30ms per image
echo.
pause
goto :menu

:process_single
echo.
echo Processing single image...
echo Input: %IMAGE_PATH%

REM Check if file exists
if not exist "%IMAGE_PATH%" (
    echo ERROR: File not found: %IMAGE_PATH%
    echo.
    pause
    goto :menu
)

REM Convert Windows path to WSL path
set "WSL_IMAGE_PATH=%IMAGE_PATH%"
set "WSL_IMAGE_PATH=!WSL_IMAGE_PATH:C:\=/mnt/c/!"
set "WSL_IMAGE_PATH=!WSL_IMAGE_PATH:D:\=/mnt/d/!"
set "WSL_IMAGE_PATH=!WSL_IMAGE_PATH:E:\=/mnt/e/!"
set "WSL_IMAGE_PATH=!WSL_IMAGE_PATH:F:\=/mnt/f/!"
set "WSL_IMAGE_PATH=!WSL_IMAGE_PATH:G:\=/mnt/g/!"
set "WSL_IMAGE_PATH=!WSL_IMAGE_PATH:H:\=/mnt/h/!"
set "WSL_IMAGE_PATH=!WSL_IMAGE_PATH:\=/!"

echo WSL path: !WSL_IMAGE_PATH!
echo.

echo Starting MUSIQ GPU inference...
echo ========================================

REM Run MUSIQ
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python scripts/python/run_musiq_gpu.py --image '!WSL_IMAGE_PATH!'"

echo.
echo ========================================
echo Single image processing completed!
echo ========================================
echo.
pause
goto :menu

:process_multiple
echo.
echo Processing multiple images...
echo Input folder: %FOLDER_PATH%

REM Check if folder exists
if not exist "%FOLDER_PATH%" (
    echo ERROR: Folder not found: %FOLDER_PATH%
    echo.
    pause
    goto :menu
)

REM Convert Windows path to WSL path
set "WSL_FOLDER_PATH=%FOLDER_PATH%"
set "WSL_FOLDER_PATH=!WSL_FOLDER_PATH:C:\=/mnt/c/!"
set "WSL_FOLDER_PATH=!WSL_FOLDER_PATH:D:\=/mnt/d/!"
set "WSL_FOLDER_PATH=!WSL_FOLDER_PATH:E:\=/mnt/e/!"
set "WSL_FOLDER_PATH=!WSL_FOLDER_PATH:F:\=/mnt/f/!"
set "WSL_FOLDER_PATH=!WSL_FOLDER_PATH:G:\=/mnt/g/!"
set "WSL_FOLDER_PATH=!WSL_FOLDER_PATH:H:\=/mnt/h/!"
set "WSL_FOLDER_PATH=!WSL_FOLDER_PATH:\=/!"

echo WSL path: !WSL_FOLDER_PATH!
echo.

echo Starting batch MUSIQ GPU inference...
echo ========================================

REM Run MUSIQ on all images in folder
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && for img in '!WSL_FOLDER_PATH!'/*.{jpg,jpeg,png,bmp,tiff}; do if [ -f \"\$img\" ]; then echo \"Processing: \$img\"; python scripts/python/run_musiq_gpu.py --image \"\$img\"; echo; fi; done"

echo.
echo ========================================
echo Batch processing completed!
echo ========================================
echo.
pause
goto :menu

:exit
echo.
echo Goodbye!
exit /b 0
