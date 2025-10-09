@echo off
setlocal enabledelayedexpansion

echo ========================================
echo    VILA Image Aesthetic Assessment
echo ========================================
echo.

REM Check if image path is provided
if "%~1"=="" (
    echo Usage: run_vila.bat "C:\Path\To\Image.jpg"
    echo.
    echo Example: run_vila.bat "D:\Photos\sample.jpg"
    echo.
    pause
    exit /b 1
)

set "IMAGE_PATH=%~1"

REM Check if image exists
if not exist "%IMAGE_PATH%" (
    echo ERROR: Image file not found: %IMAGE_PATH%
    echo.
    pause
    exit /b 1
)

echo Running VILA model on: %IMAGE_PATH%
echo.
echo Note: VILA model requires Kaggle authentication.
echo If not configured, see docs/vila/README_VILA.md for setup instructions.
echo.

REM Check if we're in WSL environment or Windows
where wsl >nul 2>&1
if %errorlevel% == 0 (
    echo Using WSL environment for VILA processing...
    echo.
    
    REM Convert Windows path to WSL path (handle any drive letter)
    set "WSL_PATH=%IMAGE_PATH%"
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
    
    REM Run VILA in WSL with TensorFlow virtual environment
    wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python run_vila.py --image '!WSL_PATH!'"
) else (
    echo Using Windows Python environment for VILA processing...
    echo Warning: VILA may not work without proper TensorFlow setup in Windows.
    echo.
    
    REM Get the directory where this batch file is located
    set "SCRIPT_DIR=%~dp0"
    
    REM Run VILA with default model
    python "%SCRIPT_DIR%run_vila.py" --image "%IMAGE_PATH%"
)

echo.
echo Press any key to exit...
pause >nul

