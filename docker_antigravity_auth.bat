@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ========================================================
echo   Antigravity CLI auth for Docker WebUI (agent cull)
echo ========================================================
echo   OAuth tokens are stored on the HOST at:
echo     %%USERPROFILE%%\.gemini
echo   and mounted into the container as /root/.gemini via
echo   GEMINI_CONFIG_SOURCE in .env — they survive image rebuild
echo   and "docker compose up --force-recreate webui".
echo.
echo   One-time interactive login in the container is enough.
echo   After that, use docker_refresh_webui.bat as usual.
echo ========================================================
echo.

call :ensure_gemini_env
if errorlevel 1 exit /b 1

docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running. Start Docker Desktop, then retry.
    pause
    exit /b 1
)

echo [INFO] Ensuring webui container is up...
docker compose up -d webui
if errorlevel 1 (
    echo [ERROR] docker compose up -d webui failed.
    pause
    exit /b 1
)

docker exec image-scoring-webui agy --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] agy not found in webui container. Run docker_refresh_webui.bat to rebuild the image.
    pause
    exit /b 1
)

echo [INFO] Checking agy authentication in container...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$out = docker exec image-scoring-webui agy -p 'hello' 2>&1 | Out-String; if ($out -match 'Authentication required|Waiting for authentication') { exit 1 }; exit 0"
if errorlevel 1 (
    echo.
    echo [INFO] Interactive login required ^(browser + paste code below^).
    echo       Paste the authorization code when agy prompts — not into a new PowerShell line.
    echo.
    docker exec -it image-scoring-webui agy -p "hello"
    if errorlevel 1 (
        echo [ERROR] agy login failed.
        pause
        exit /b 1
    )
) else (
    echo [SUCCESS] agy is already authenticated in the container.
)

echo.
echo [INFO] Verifying after login...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$out = docker exec image-scoring-webui agy -p 'hello' 2>&1 | Out-String; if ($out -match 'Authentication required|Waiting for authentication') { Write-Host '[ERROR] Still not authenticated.'; exit 1 }; Write-Host '[SUCCESS] agy hello OK — creds persist under %USERPROFILE%\.gemini'; exit 0"
if errorlevel 1 (
    pause
    exit /b 1
)

echo.
echo Done. Rebuilds are safe: keep GEMINI_CONFIG_SOURCE in .env and do not run
echo "docker compose down -v" ^(that removes Postgres, not .gemini, but avoid -v anyway^).
echo.
pause
exit /b 0

:ensure_gemini_env
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] Creating .env from .env.example...
        copy /Y ".env.example" ".env" >nul
    )
)
if not exist ".env" (
    echo [ERROR] No .env file. Copy .env.example to .env and set GEMINI_CONFIG_SOURCE.
    exit /b 1
)
findstr /B /I /C:"GEMINI_CONFIG_SOURCE=" ".env" >nul 2>&1
if not errorlevel 1 exit /b 0
findstr /B /I /C:"GEMINI_API_KEY=" ".env" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] GEMINI_API_KEY set in .env — OAuth mount optional.
    exit /b 0
)
if exist "%USERPROFILE%\.gemini" goto :append_gemini_config
echo [ERROR] Set GEMINI_CONFIG_SOURCE or GEMINI_API_KEY in .env, or create %%USERPROFILE%%\.gemini
exit /b 1
:append_gemini_config
for /f "delims=" %%G in ('powershell -NoProfile -Command "($env:USERPROFILE -replace '\\','/') + '/.gemini'"') do (
    echo [INFO] Appending GEMINI_CONFIG_SOURCE=%%G to .env
    echo GEMINI_CONFIG_SOURCE=%%G>> ".env"
)
exit /b 0
