@echo off
setlocal enabledelayedexpansion

echo ========================================
echo    MUSIQ Image Gallery Generator
echo ========================================
echo.

REM Check if folder path is provided
if "%~1"=="" (
    echo Usage: create_gallery.bat "C:\Path\To\Your\Images"
    echo.
    echo Example: create_gallery.bat "D:\Photos\Export\2025"
    echo.
    pause
    exit /b 1
)

set "INPUT_FOLDER=%~1"
set "OUTPUT_FILE=%~1\gallery.html"

echo Input folder: %INPUT_FOLDER%
echo Output file: %OUTPUT_FILE%
echo.

REM Check if input folder exists
if not exist "%INPUT_FOLDER%" (
    echo ERROR: Folder does not exist: %INPUT_FOLDER%
    echo.
    pause
    exit /b 1
)

echo Creating gallery for images in: %INPUT_FOLDER%
echo.

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"

REM First, run MUSIQ models on all images in the folder
echo Step 1: Running MUSIQ models on all images...
echo This may take a while depending on the number of images...
echo.

REM Check if we're in WSL environment or Windows
where wsl >nul 2>&1
if %errorlevel% == 0 (
    echo Using WSL environment for MUSIQ processing...
    REM Convert Windows path to WSL path
    set "WSL_PATH=%INPUT_FOLDER%"
    set "WSL_PATH=!WSL_PATH:D:\=/mnt/d/!"
    set "WSL_PATH=!WSL_PATH:\=/!"
    wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python batch_process_images.py --input-dir '!WSL_PATH!' --output-dir '!WSL_PATH!'"
) else (
    echo Using Windows Python environment for MUSIQ processing...
    python "%SCRIPT_DIR%batch_process_images.py" --input-dir "%INPUT_FOLDER%" --output-dir "%INPUT_FOLDER%"
)

echo.
echo Step 2: Generating HTML gallery...
echo.

REM Run the Python gallery generator
echo Running gallery generator...
python "%SCRIPT_DIR%gallery_generator.py" "%INPUT_FOLDER%"

REM Check if gallery was created successfully
if exist "%OUTPUT_FILE%" (
    echo.
    echo ✅ SUCCESS: Gallery created successfully!
    echo 📁 Output file: %OUTPUT_FILE%
    echo.
    echo Opening gallery in your default web browser...
    start "" "%OUTPUT_FILE%"
    echo.
    echo Gallery opened! You can now browse your images with quality scores.
) else (
    echo.
    echo ❌ ERROR: Failed to create gallery
    echo Please check that the folder contains JSON files with image data.
    echo Make sure Python is installed and accessible from command line.
)

echo.
echo Press any key to exit...
pause >nul