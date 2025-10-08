@echo off
REM MUSIQ GPU Drag-and-Drop Runner for Windows 11 + WSL2
REM Simply drag and drop an image file onto this script to run MUSIQ with GPU acceleration

echo ========================================
echo    MUSIQ GPU Drag-and-Drop Runner
echo    WSL2 + Ubuntu + TensorFlow GPU
echo ========================================
echo.

REM Check if any files were dropped
if "%~1"=="" (
    echo No files dropped. Please drag and drop an image file onto this script.
    echo.
    echo Supported formats: JPG, JPEG, PNG, BMP, TIFF
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

echo Starting MUSIQ GPU inference...
echo ========================================

REM Run MUSIQ through WSL2
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python run_musiq_gpu.py --image '%WSL_PATH%'"

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
pause
