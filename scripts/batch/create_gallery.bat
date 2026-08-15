@echo off
cd /d "%~dp0..\.."
setlocal enabledelayedexpansion

echo ========================================
echo  Image Quality Gallery Generator
echo  MUSIQ + VILA Multi-Model Scoring
echo  + Nikon NEF Rating (1-5 stars)
echo ========================================
echo.

REM Check if folder path is provided
if "%~1"=="" (
    echo Usage: create_gallery.bat "C:\Path\To\Your\Images"
    echo.
    echo Example: create_gallery.bat "D:\Photos\Export\2025"
    echo.
    echo Features:
    echo - Processes all image formats (JPG, PNG, TIFF, RAW)
    echo - Automatically rates Nikon NEF files (1-5 stars)
    echo - Generates interactive HTML gallery
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
echo Models used:
echo   - MUSIQ models: SPAQ, AVA, KONIQ, PAQ2PIQ
echo   - VILA model: VILA (if Kaggle auth configured)
echo.

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"

REM First, run all models on all images in the folder
echo Step 1: Running image quality assessment...
echo   - Processing with MUSIQ models (SPAQ, AVA, KONIQ, PAQ2PIQ)
echo   - Processing with VILA model (VILA)
echo.
echo Note: VILA models require Kaggle authentication.
echo If not configured, VILA will be skipped (MUSIQ will still work).
echo See docs/vila/README_VILA.md for Kaggle setup instructions.
echo.
echo This may take a while depending on the number of images...
echo.

echo Using image-scoring-gpu-shell for multi-model processing...
call "%~dp0docker_gpu_run.bat" scripts/python/batch_process_images.py --input-dir "%INPUT_FOLDER%" --output-dir "%INPUT_FOLDER%" --rate-nef

echo.
echo Step 2: Generating HTML gallery...
echo.

REM Run the Python gallery generator
echo Running gallery generator...
python "scripts\python\gallery_generator.py" "%INPUT_FOLDER%"

REM Check if gallery was created successfully
if exist "%OUTPUT_FILE%" (
    echo.
    echo [SUCCESS] Gallery created successfully!
    echo Output file: %OUTPUT_FILE%
    echo.
    echo Gallery includes scores from:
    echo   + MUSIQ models ^(always included^)
    echo   + VILA model ^(if Kaggle auth configured^)
    echo.
    echo Opening gallery in your default web browser...
    start "" "%OUTPUT_FILE%"
    echo.
    echo Gallery opened! You can now browse your images with quality scores.
    echo Images are sorted by weighted score from all available models.
) else (
    echo.
    echo [ERROR] Failed to create gallery
    echo Please check that the folder contains JSON files with image data.
    echo Make sure Python is installed and accessible from command line.
    echo.
    echo If VILA models failed to load, check README_VILA.md for setup.
)

echo.
echo Press any key to exit...
pause >nul