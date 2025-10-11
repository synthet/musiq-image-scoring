@echo off
echo ========================================
echo    VILA Integration Test Script
echo ========================================
echo.
echo This script tests the VILA model integration.
echo.

python "%~dp0..\..\tests\test_vila.py"

echo.
echo Press any key to exit...
pause >nul

