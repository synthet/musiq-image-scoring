@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM Required for Dockerfile cache mounts (RUN --mount=type=cache)
if not defined DOCKER_BUILDKIT set "DOCKER_BUILDKIT=1"

if not defined WEBUI_OPEN_UI set "WEBUI_OPEN_UI=browser"

echo ========================================================
echo   Vexlum Scoring - Docker refresh (frontend + webui)
echo ========================================================
echo   Rebuilds Vite SPA to static/app, rebuilds webui image,
echo   recreates webui container. Postgres data volume is kept
echo   (no docker compose down -v).
echo.
echo   Prerequisites: Docker Desktop, Node/npm on PATH.
echo   DB: compose Postgres service (pgvector). Legacy Firebird: run_firebird.bat if needed.
echo.
echo   Optional environment variables:
echo     SKIP_FRONTEND_BUILD=1   skip npm (Python/static unchanged)
echo     DOCKER_BUILD_NO_CACHE=1   full rebuild layers (avoid unless needed)
echo     FRONTEND_CI=1             run npm ci before npm run build
echo     WEBUI_READY_TIMEOUT_SEC=N  max seconds to wait for http://localhost:7860 (default 360)
echo     DOCKER_READY_TIMEOUT_SEC=N max seconds to wait for Docker daemon (default 180)
echo     SKIP_DOCKER_START=1        fail if Docker is down; do not auto-start Desktop
echo   Docker: Dockerfile uses BuildKit cache mounts for apt and pip — normal
echo   builds reuse downloaded packages. Ensure DOCKER_BUILDKIT=1 (Docker Desktop default).
echo ========================================================
echo.

docker info >nul 2>&1
if errorlevel 1 (
    if not defined DOCKER_READY_TIMEOUT_SEC set "DOCKER_READY_TIMEOUT_SEC=180"
    echo [INFO] Docker is not running. Attempting to start Docker Desktop...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\powershell\Ensure-DockerDesktop.ps1" -TimeoutSec %DOCKER_READY_TIMEOUT_SEC%
    if errorlevel 1 (
        echo [ERROR] Could not start Docker Desktop or the daemon did not become ready in time.
        pause
        exit /b 1
    )
)

if /I "!SKIP_FRONTEND_BUILD!"=="1" (
    echo [INFO] SKIP_FRONTEND_BUILD=1 - skipping frontend npm build.
) else (
    where npm >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] npm not found on PATH. Install Node.js or set SKIP_FRONTEND_BUILD=1.
        pause
        exit /b 1
    )
    pushd frontend
    if /I "!FRONTEND_CI!"=="1" (
        echo [INFO] FRONTEND_CI=1: running npm ci...
        call npm ci
        if errorlevel 1 (
            echo [ERROR] npm ci failed.
            popd
            pause
            exit /b 1
        )
    )
    echo [INFO] Building frontend: npm run build
    call npm run build
    if errorlevel 1 (
        echo [ERROR] npm run build failed.
        popd
        pause
        exit /b 1
    )
    popd
)

if /I "!DOCKER_BUILD_NO_CACHE!"=="1" (
    echo [INFO] DOCKER_BUILD_NO_CACHE=1: docker compose build --no-cache webui...
    docker compose build --no-cache webui
) else (
    echo [INFO] docker compose build webui...
    docker compose build webui
)
if errorlevel 1 (
    echo [ERROR] docker compose build webui failed.
    pause
    exit /b 1
)

echo [INFO] Starting/recreating webui; db container and postgres_data unchanged.
docker compose up -d webui
if errorlevel 1 (
    echo [ERROR] docker compose up -d webui failed.
    pause
    exit /b 1
)

if not defined WEBUI_READY_TIMEOUT_SEC set "WEBUI_READY_TIMEOUT_SEC=360"
echo [INFO] Waiting for WebUI at http://localhost:7860 (up to %WEBUI_READY_TIMEOUT_SEC%s; first boot after rebuild is often slow^) ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$uri='http://localhost:7860/api/health'; $max=$env:WEBUI_READY_TIMEOUT_SEC; if ($max -notmatch '^\d+$' -or [int]$max -lt 60) { $max=360 }; $max=[int]$max; for ($i=0; $i -lt $max; $i++) { try { Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } }; Write-Host '[ERROR] WebUI did not become ready in time.'; exit 1"
if errorlevel 1 (
    echo [ERROR] Timeout waiting for WebUI. Check: docker compose logs webui
    pause
    exit /b 1
)

call :webui_open_ui

echo.
echo [SUCCESS] Docker webui refreshed. Containers are running detached.
echo           Logs: docker compose logs -f webui
echo.
pause
goto :eof

:webui_open_ui
if /I "%WEBUI_OPEN_UI%"=="none" (
    echo [INFO] WEBUI_OPEN_UI=none - not opening browser or Electron.
    goto :eof
)
if /I "%WEBUI_OPEN_UI%"=="electron" (
    call :webui_open_electron
    goto :eof
)
echo [INFO] Opening browser...
start "" "http://localhost:7860"
goto :eof

:webui_open_electron
pushd "%~dp0.."
set "GALLERY="
if exist "image-scoring-gallery\package.json" set "GALLERY=%CD%\image-scoring-gallery"
if not defined GALLERY if exist "electron-image-scoring\package.json" set "GALLERY=%CD%\electron-image-scoring"
popd
if not defined GALLERY (
    echo [ERROR] WEBUI_OPEN_UI=electron but no sibling gallery folder image-scoring-gallery.
    exit /b 1
)
where npx >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npx not found on PATH. Install Node.js or set WEBUI_OPEN_UI=browser.
    exit /b 1
)
echo [INFO] Opening WebUI in Electron...
set "WEBUI_GALLERY_DIR=%GALLERY%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:COMSPEC -ArgumentList '/c','set ELECTRON_IS_DEV=1^&^& npx electron . --webui-shell=http://127.0.0.1:7860/ui/' -WorkingDirectory $env:WEBUI_GALLERY_DIR"
exit /b 0
