@echo off
setlocal

echo ============================================================
echo  Vexlum Scoring: Docker Environment Smoke Test (WSL)
echo ============================================================

REM 1. Check if WSL is available
where wsl >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] WSL not found. Please install WSL 2 to use Docker integration.
    pause
    exit /b 1
)

REM 2. Ensure scripts are executable in WSL
echo [INFO] Preparing scripts in WSL...
wsl chmod +x ./scripts/wsl/docker_smoke_test.sh

REM 3. Run the smoke test in WSL
echo [INFO] Transitioning to WSL for environment checks...
echo.

wsl bash ./scripts/wsl/docker_smoke_test.sh

if %ERRORLEVEL% neq 0 (
    echo.
    echo [FAIL] Docker Smoke Test failed. Please check the logs above.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [SUCCESS] Your environment is ready for Docker-based Vexlum Scoring!
echo.
pause
