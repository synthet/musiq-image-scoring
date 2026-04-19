@echo off
setlocal enabledelayedexpansion

set POSTGRES_HOST=127.0.0.1
set POSTGRES_PORT=5432
set POSTGRES_DATABASE=image_scoring
set POSTGRES_USER=postgres
set POSTGRES_PASSWORD=postgres

tools\toolbox.exe --prebuilt postgres --stdio
