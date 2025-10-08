@echo off
REM Batch process all images in D:\Photos\Export\2025 with comprehensive logging
REM All output (including errors and warnings) will be redirected to a log file

echo ========================================
echo    MUSIQ Batch Image Processor
echo    Processing all images in directory
echo ========================================
echo.

REM Set the input directory (JSON files will be saved in the same directory by default)
set "INPUT_DIR=D:\Photos\Export\2025"
set "OUTPUT_DIR=D:\Photos\Export\2025"

REM Check if input directory exists
if not exist "%INPUT_DIR%" (
    echo ERROR: Input directory not found: %INPUT_DIR%
    echo.
    pause
    exit /b 1
)

echo Input directory: %INPUT_DIR%
echo Output directory: %OUTPUT_DIR%
echo.

REM Generate log file name with current date and time
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "YY=%dt:~2,2%" & set "YYYY=%dt:~0,4%" & set "MM=%dt:~4,2%" & set "DD=%dt:~6,2%"
set "HH=%dt:~8,2%" & set "Min=%dt:~10,2%" & set "Sec=%dt:~12,2%"
set "LOG_FILE=musiq_batch_log_%YYYY%%MM%%DD%_%HH%%Min%%Sec%.log"

echo Log file: %LOG_FILE%
echo.

echo Starting batch processing...
echo All output will be logged to: %LOG_FILE%
echo.

REM Run the batch processor through WSL2 and redirect all output to log file
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python batch_process_images.py --input-dir '/mnt/d/Photos/Export/2025' --output-dir '/mnt/d/Photos/Export/2025' --log-file '%LOG_FILE%'" > "%LOG_FILE%" 2>&1

REM Check if the log file was created and show the last few lines
if exist "%LOG_FILE%" (
    echo.
    echo ========================================
    echo Batch processing completed!
    echo ========================================
    echo.
    echo Log file created: %LOG_FILE%
    echo.
    echo Last few lines of the log:
    echo ----------------------------------------
    powershell -command "Get-Content '%LOG_FILE%' | Select-Object -Last 10"
    echo ----------------------------------------
    echo.
    echo To view the full log, open: %LOG_FILE%
) else (
    echo ERROR: Log file was not created. Check for errors.
)

echo.
pause
