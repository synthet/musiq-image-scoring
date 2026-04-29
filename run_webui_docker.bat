@echo off
setlocal
cd /d "%~dp0"

REM RunWebUI.exe sets this; plain shortcut should open the browser unless you set User env.
if not defined WEBUI_OPEN_UI set "WEBUI_OPEN_UI=browser"

echo ========================================================
echo   Vexlum Scoring - Docker Launcher
echo ========================================================
echo.

docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker Desktop is not running. Please start it first.
    pause
    exit /b 1
)

echo [INFO] Checking if WebUI is already up...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri 'http://localhost:7860' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel% equ 0 (
    echo [INFO] WebUI is already running at http://localhost:7860
    call :webui_open_ui
    exit /b 0
)

docker image inspect image-scoring:latest >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Image image-scoring:latest not found.
    echo         Run docker_rebuild.bat first to build the image.
    pause
    exit /b 1
)

echo [INFO] Starting containers (detached)...
docker compose up -d
if %errorlevel% neq 0 (
    echo [ERROR] docker compose up -d failed.
    pause
    exit /b 1
)

echo [INFO] Waiting for WebUI at http://localhost:7860 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$uri='http://localhost:7860'; $max=60; for ($i=0; $i -lt $max; $i++) { try { Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } }; Write-Host '[ERROR] WebUI did not become ready in time.'; exit 1"
if %errorlevel% neq 0 (
    echo [ERROR] Timeout waiting for WebUI. Check: docker compose logs webui
    pause
    exit /b 1
)

call :webui_open_ui

echo.
echo [INFO] Tailing logs (Ctrl+C stops tail only; containers keep running).
echo.

docker compose logs -f

echo.
echo [INFO] Log tail ended.
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

REM Must be a subroutine, not inside "if (...)", so %%GALLERY%% is expanded after set, not at block parse time.
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
