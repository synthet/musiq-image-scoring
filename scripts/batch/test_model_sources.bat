@echo off
setlocal

echo ========================================
echo    Model Sources Test Script
echo    TensorFlow Hub + Kaggle Hub
echo ========================================
echo.

call "%~dp0docker_gpu_run.bat" tests/test_model_sources.py %*

echo.
echo Press any key to exit...
pause >nul
