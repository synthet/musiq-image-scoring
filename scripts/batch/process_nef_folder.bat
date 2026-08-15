@echo off
cd /d "%~dp0..\.."
setlocal enabledelayedexpansion

echo ========================================
echo  NEF Folder Processor
echo  MUSIQ + VILA Multi-Model Scoring
echo  + Nikon NEF Rating (1-5 stars)
echo ========================================
echo.

REM Check if folder path is provided
if "%~1"=="" (
    echo Usage: Drag and drop a folder containing NEF files onto this script
    echo.
    echo Or use: process_nef_folder.bat "C:\Path\To\Your\NEF\Folder"
    echo.
    pause
    exit /b 1
)

set "INPUT_FOLDER=%~1"

echo Processing folder: %INPUT_FOLDER%
echo.

REM Check if input folder exists
if not exist "%INPUT_FOLDER%" (
    echo ERROR: Folder does not exist: %INPUT_FOLDER%
    echo.
    pause
    exit /b 1
)

echo Step 1: Processing NEF files with MUSIQ models and rating...
echo.

call "%~dp0docker_gpu_run.bat" scripts/python/batch_process_images.py --input-dir "%INPUT_FOLDER%" --output-dir "%INPUT_FOLDER%" --rate-nef

echo.
echo Step 2: Generating HTML gallery...
echo.

REM Run the Python gallery generator
python "scripts\python\gallery_generator.py" "%INPUT_FOLDER%"

echo.
echo [SUCCESS] Processing completed!
echo Output file: %INPUT_FOLDER%\gallery.html
echo.

REM Open the gallery
if exist "%INPUT_FOLDER%\gallery.html" (
    echo Opening gallery in your default web browser...
    start "" "%INPUT_FOLDER%\gallery.html"
) else (
    echo [ERROR] Gallery file not found
)

echo.
pause
