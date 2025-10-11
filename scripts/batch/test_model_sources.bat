@echo off
setlocal enabledelayedexpansion

echo ========================================
echo    Model Sources Test Script
echo    TensorFlow Hub + Kaggle Hub
echo ========================================
echo.

REM Get the directory where this batch file is located
set "SCRIPT_DIR=%~dp0"

REM Check if we're in WSL environment or Windows
where wsl >nul 2>&1
if %errorlevel% == 0 (
    echo Using WSL environment for testing...
    echo.
    
    REM Parse command line arguments
    set "ARGS="
    
    :parse_args
    if "%~1"=="" goto end_parse
    if "%~1"=="--test-kaggle" set "ARGS=!ARGS! --test-kaggle"
    if "%~1"=="--skip-download" set "ARGS=!ARGS! --skip-download"
    if "%~1"=="--verbose" set "ARGS=!ARGS! --verbose"
    shift
    goto parse_args
    
    :end_parse
    
    REM Run test in WSL with TensorFlow virtual environment
    wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python tests/test_model_sources.py !ARGS!"
) else (
    echo Using Windows Python environment for testing...
    echo Warning: TensorFlow may not be properly configured in Windows.
    echo WSL is recommended for accurate testing.
    echo.
    
    REM Run test with Windows Python
    python "%~dp0..\..\tests\test_model_sources.py" %*
)

echo.
echo Press any key to exit...
pause >nul

