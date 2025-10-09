@echo off
REM MUSIQ Multi-Model Drag-and-Drop Runner for Windows 11 + WSL2
REM Runs all available MUSIQ models on an image and saves results to JSON
REM Simply drag and drop an image file onto this script

echo ========================================
echo    MUSIQ Multi-Model Drag-and-Drop Runner
echo    WSL2 + Ubuntu + TensorFlow GPU
echo ========================================
echo.

REM Check if any files were dropped
if "%~1"=="" (
    echo No files dropped. Please drag and drop an image file onto this script.
    echo.
    echo Supported formats: JPG, JPEG, PNG, BMP, TIFF
    echo.
    echo This script will run all available MUSIQ models:
    echo   - SPAQ (range: 1-5)
    echo   - AVA (range: 1-10)
    echo   - KONIQ (range: 1-5)
    echo   - PAQ2PIQ (range: 1-5)
    echo.
    echo Results will be saved as JSON file with same name as image.
    echo.
    pause
    exit /b 1
)

REM Process each dropped file
:process_file
set "FILE_PATH=%~1"

echo Processing: %FILE_PATH%

REM Check if file exists
if not exist "%FILE_PATH%" (
    echo ERROR: File not found: %FILE_PATH%
    echo.
    goto :next_file
)

REM Check if it's an image file
set "EXTENSION=%~x1"
set "EXTENSION=%EXTENSION:.=%"
if /i not "%EXTENSION%"=="jpg" if /i not "%EXTENSION%"=="jpeg" if /i not "%EXTENSION%"=="png" if /i not "%EXTENSION%"=="bmp" if /i not "%EXTENSION%"=="tiff" (
    echo WARNING: %FILE_PATH% may not be a supported image format
    echo Supported formats: JPG, JPEG, PNG, BMP, TIFF
    echo.
)

REM Convert Windows path to WSL path
set "WSL_PATH=%FILE_PATH%"
set "WSL_PATH=%WSL_PATH:C:\=/mnt/c/%"
set "WSL_PATH=%WSL_PATH:D:\=/mnt/d/%"
set "WSL_PATH=%WSL_PATH:E:\=/mnt/e/%"
set "WSL_PATH=%WSL_PATH:F:\=/mnt/f/%"
set "WSL_PATH=%WSL_PATH:G:\=/mnt/g/%"
set "WSL_PATH=%WSL_PATH:H:\=/mnt/h/%"
set "WSL_PATH=%WSL_PATH:\=/%"

echo WSL path: %WSL_PATH%
echo.

echo Starting MUSIQ multi-model inference...
echo ========================================

REM Run MUSIQ multi-model through WSL2
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python run_all_musiq_models.py --image '%WSL_PATH%' --output-dir /mnt/d/Projects/image-scoring"

echo.
echo ========================================
echo Processing completed for: %FILE_PATH%
echo ========================================
echo.

:next_file
shift
if not "%~1"=="" goto :process_file

echo All files processed!
echo.
echo JSON results files have been saved in the source folder.
echo.
pause
