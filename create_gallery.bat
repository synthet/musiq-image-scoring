@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  Image Quality Gallery Generator
echo  MUSIQ + VILA Multi-Model Scoring
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
echo See README_VILA.md for Kaggle setup instructions.
echo.
echo This may take a while depending on the number of images...
echo.

REM Check if we're in WSL environment or Windows
where wsl >nul 2>&1
if %errorlevel% == 0 (
    echo Using WSL environment for multi-model processing...
    REM Convert Windows path to WSL path (handle any drive letter)
    set "WSL_PATH=%INPUT_FOLDER%"
    REM Convert C:\ to /mnt/c/, D:\ to /mnt/d/, etc.
    for %%D in (A B C D E F G H I J K L M N O P Q R S T U V W X Y Z) do (
        set "WSL_PATH=!WSL_PATH:%%D:\=/mnt/%%D/!"
    )
    REM Convert remaining backslashes to forward slashes
    set "WSL_PATH=!WSL_PATH:\=/!"
    REM Convert to lowercase for drive letter
    set "WSL_PATH=!WSL_PATH:/mnt/A/=/mnt/a/!"
    set "WSL_PATH=!WSL_PATH:/mnt/B/=/mnt/b/!"
    set "WSL_PATH=!WSL_PATH:/mnt/C/=/mnt/c/!"
    set "WSL_PATH=!WSL_PATH:/mnt/D/=/mnt/d/!"
    set "WSL_PATH=!WSL_PATH:/mnt/E/=/mnt/e/!"
    set "WSL_PATH=!WSL_PATH:/mnt/F/=/mnt/f/!"
    set "WSL_PATH=!WSL_PATH:/mnt/G/=/mnt/g/!"
    set "WSL_PATH=!WSL_PATH:/mnt/H/=/mnt/h/!"
    set "WSL_PATH=!WSL_PATH:/mnt/I/=/mnt/i/!"
    set "WSL_PATH=!WSL_PATH:/mnt/J/=/mnt/j/!"
    set "WSL_PATH=!WSL_PATH:/mnt/K/=/mnt/k/!"
    set "WSL_PATH=!WSL_PATH:/mnt/L/=/mnt/l/!"
    set "WSL_PATH=!WSL_PATH:/mnt/M/=/mnt/m/!"
    set "WSL_PATH=!WSL_PATH:/mnt/N/=/mnt/n/!"
    set "WSL_PATH=!WSL_PATH:/mnt/O/=/mnt/o/!"
    set "WSL_PATH=!WSL_PATH:/mnt/P/=/mnt/p/!"
    set "WSL_PATH=!WSL_PATH:/mnt/Q/=/mnt/q/!"
    set "WSL_PATH=!WSL_PATH:/mnt/R/=/mnt/r/!"
    set "WSL_PATH=!WSL_PATH:/mnt/S/=/mnt/s/!"
    set "WSL_PATH=!WSL_PATH:/mnt/T/=/mnt/t/!"
    set "WSL_PATH=!WSL_PATH:/mnt/U/=/mnt/u/!"
    set "WSL_PATH=!WSL_PATH:/mnt/V/=/mnt/v/!"
    set "WSL_PATH=!WSL_PATH:/mnt/W/=/mnt/w/!"
    set "WSL_PATH=!WSL_PATH:/mnt/X/=/mnt/x/!"
    set "WSL_PATH=!WSL_PATH:/mnt/Y/=/mnt/y/!"
    set "WSL_PATH=!WSL_PATH:/mnt/Z/=/mnt/z/!"
    wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python batch_process_images.py --input-dir '!WSL_PATH!' --output-dir '!WSL_PATH!'"
) else (
    echo Using Windows Python environment for multi-model processing...
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
    echo Gallery includes scores from:
    echo   ✓ MUSIQ models (always included)
    echo   ✓ VILA model (if Kaggle auth configured)
    echo.
    echo Opening gallery in your default web browser...
    start "" "%OUTPUT_FILE%"
    echo.
    echo Gallery opened! You can now browse your images with quality scores.
    echo Images are sorted by weighted score from all available models.
) else (
    echo.
    echo ❌ ERROR: Failed to create gallery
    echo Please check that the folder contains JSON files with image data.
    echo Make sure Python is installed and accessible from command line.
    echo.
    echo If VILA models failed to load, check README_VILA.md for setup.
)

echo.
echo Press any key to exit...
pause >nul