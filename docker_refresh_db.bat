@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ========================================================
echo   Vexlum Scoring - Docker refresh (db)
echo ========================================================
echo   Recreates the Postgres db container to apply compose
echo   changes (e.g. shm_size). Postgres data volume is kept.
echo ========================================================
echo.

docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Desktop is not running. Please start it first.
    pause
    exit /b 1
)

echo [INFO] Pulling database image if needed...
docker compose pull db

echo [INFO] Recreating and starting db container...
docker compose up -d --force-recreate db
if errorlevel 1 (
    echo [ERROR] docker compose up -d db failed.
    pause
    exit /b 1
)

if not defined DB_READY_TIMEOUT_SEC set "DB_READY_TIMEOUT_SEC=60"
echo [INFO] Waiting for database to be ready (up to %DB_READY_TIMEOUT_SEC%s) ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$max=$env:DB_READY_TIMEOUT_SEC; if ($max -notmatch '^\d+$') { $max=60 }; $max=[int]$max; for ($i=0; $i -lt $max; $i++) { $out = (docker exec image-scoring-postgres pg_isready -U postgres 2>&1); if ($LASTEXITCODE -eq 0) { exit 0 } else { Start-Sleep -Seconds 1 } }; Write-Host '[ERROR] DB did not become ready.'; exit 1"
if errorlevel 1 (
    echo [ERROR] Timeout waiting for DB. Check: docker compose logs db
    pause
    exit /b 1
)

echo [INFO] (Optional) Restarting webui in case it lost DB connection...
docker compose restart webui

echo.
echo [SUCCESS] Database container refreshed (and webui restarted).
echo           Logs: docker compose logs -f db
echo.
pause
goto :eof
