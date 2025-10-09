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
