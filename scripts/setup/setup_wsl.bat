@echo off
setlocal enabledelayedexpansion

REM Setup WSL environment (~/.venvs/tf) for Vexlum WebUI
REM Run from Windows; invokes WSL to create venv and install dependencies.

REM Resolve project root (script is in scripts/setup/)
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."
cd /d "%PROJECT_ROOT%"
set "PROJECT_ROOT=%CD%"

REM Convert to WSL path (e.g. D:\path\to\repo -> /mnt/d/path/to/repo)
set "WSL_PATH=!PROJECT_ROOT:\=/!"
set "WSL_PATH=!WSL_PATH::=!"
set "WSL_PATH=/mnt/!WSL_PATH!"
set "WSL_PATH=!WSL_PATH:/mnt/C=/mnt/c!"
set "WSL_PATH=!WSL_PATH:/mnt/D=/mnt/d!"
set "WSL_PATH=!WSL_PATH:/mnt/E=/mnt/e!"
set "WSL_PATH=!WSL_PATH:/mnt/F=/mnt/f!"
if "!WSL_PATH:~-1!"=="/" set "WSL_PATH=!WSL_PATH:~0,-1!"

echo.
echo === WSL Environment Setup (^~/.venvs/tf^) ===
echo Project root: %PROJECT_ROOT%
echo WSL path: !WSL_PATH!
echo.

REM Check WSL is available
wsl -e true 2>nul
if errorlevel 1 (
    echo ERROR: WSL is not available. Install WSL2 with Ubuntu first.
    echo   wsl --install -d Ubuntu
    pause
    exit /b 1
)
echo [OK] WSL is available.
echo.

REM Run setup in WSL
echo [1/4] Installing python3-venv if needed...
wsl -e bash -c "sudo apt-get update -qq && sudo apt-get install -y python3-venv python3-pip build-essential 2>/dev/null || true"
echo.

echo [2/4] Creating virtual environment at ~/.venvs/tf...
wsl -e bash -c "mkdir -p ~/.venvs && python3 -m venv ~/.venvs/tf"
if errorlevel 1 (
    echo ERROR: Failed to create ~/.venvs/tf
    pause
    exit /b 1
)
echo   Created ~/.venvs/tf
echo.

echo [3/4] Upgrading pip and installing dependencies...
set "REQ_FILE=requirements/requirements_wsl_gpu.txt"
wsl -e bash -c "test -f '!WSL_PATH!/requirements/requirements_wsl_gpu.txt'" 2>nul
if errorlevel 1 set "REQ_FILE=requirements.txt"

wsl -e bash -c "source ~/.venvs/tf/bin/activate && pip install --upgrade pip setuptools wheel && cd '!WSL_PATH!' && pip install -r !REQ_FILE!"
if errorlevel 1 (
    echo WARNING: GPU requirements may have failed. Trying CPU fallback...
    wsl -e bash -c "source ~/.venvs/tf/bin/activate && cd '!WSL_PATH!' && pip install -r requirements.txt"
    if errorlevel 1 (
        echo ERROR: pip install failed
        pause
        exit /b 1
    )
)
echo.

echo [4/4] Verifying...
wsl -e bash -c "source ~/.venvs/tf/bin/activate && python -c 'import tensorflow; print(""TensorFlow:"", tensorflow.__version__)'"
if errorlevel 1 (
    wsl -e bash -c "source ~/.venvs/tf/bin/activate && python -c 'import sys; print(sys.version)'"
)
echo.

echo === Setup complete ===
echo.
echo To launch the WebUI:
echo   run_webui.bat
echo.
echo Or from WSL:
echo   source ~/.venvs/tf/bin/activate
echo   cd !WSL_PATH!
echo   python launch.py
echo.
pause
