@echo off
setlocal enabledelayedexpansion

echo ========================================
echo    MUSIQ Image Quality Processor
echo ========================================
echo.

REM Check if folder path is provided
if "%~1"=="" (
    echo Usage: process_images.bat "C:\Path\To\Your\Images"
    echo.
    echo This will run all MUSIQ models on images in the specified folder
    echo and generate JSON files with quality scores.
    echo.
    echo Example: process_images.bat "D:\Photos\Export\2025"
    echo.
    pause
    exit /b 1
)

set "INPUT_FOLDER=%~1"

echo Input folder: %INPUT_FOLDER%
echo.

REM Check if input folder exists
if not exist "%INPUT_FOLDER%" (
    echo ERROR: Folder does not exist: %INPUT_FOLDER%
    echo.
    pause
    exit /b 1
)

echo Processing images in: %INPUT_FOLDER%
echo This will run all MUSIQ models (SPAQ, AVA, KONIQ, PAQ2PIQ) on each image.
echo This may take a while depending on the number of images...
echo.

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"

REM Check if we're in WSL environment or Windows
where wsl >nul 2>&1
if %errorlevel% == 0 (
    echo Using WSL environment for MUSIQ processing...
    echo.
    wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python batch_process_images.py --input-dir '%INPUT_FOLDER%' --output-dir '%INPUT_FOLDER%'"
) else (
    echo Using Windows Python environment for MUSIQ processing...
    echo.
    python "%SCRIPT_DIR%batch_process_images.py" --input-dir "%INPUT_FOLDER%" --output-dir "%INPUT_FOLDER%"
)

echo.
echo Processing complete!
echo JSON files with quality scores have been generated in: %INPUT_FOLDER%
echo.
echo You can now use create_gallery.bat to generate an HTML gallery from these results.
echo.

pause
