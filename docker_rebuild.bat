@echo off
setlocal
cd /d "%~dp0"

if not defined DOCKER_BUILDKIT set "DOCKER_BUILDKIT=1"

echo ========================================================
echo   Vexlum Scoring - Docker full rebuild (no cache)
echo ========================================================
echo   Stops containers, rebuilds image from scratch, starts
echo   stack in foreground. Postgres data volume is kept.
echo ========================================================
echo.

docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker Desktop is not running. Please start it first.
    pause
    exit /b 1
)

echo [INFO] Stopping containers (volumes preserved)...
docker compose down
if %errorlevel% neq 0 (
    echo [ERROR] docker compose down failed.
    pause
    exit /b 1
)

echo.
echo [INFO] Building image from scratch (--no-cache)...
docker compose build --no-cache
if %errorlevel% neq 0 (
    echo [ERROR] docker compose build failed.
    pause
    exit /b 1
)

echo.
echo [INFO] Starting containers (foreground logs)...
echo [INFO] WebUI: http://localhost:7860
echo.

docker compose up

echo.
echo [INFO] Shutdown complete.
pause
