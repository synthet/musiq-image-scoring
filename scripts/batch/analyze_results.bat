@echo off
REM Analyze JSON results from MUSIQ batch processing
REM Finds best and worst images overall and by each model

echo ========================================
echo    MUSIQ Results Analyzer
echo    Finding best and worst images
echo ========================================
echo.

for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"

echo Analyzing directory: %PROJECT_ROOT%
echo.

call "%~dp0docker_gpu_run.bat" scripts/analysis/analyze_json_results.py --directory "%PROJECT_ROOT%"

echo.
echo Analysis complete!
echo Check the generated analysis_summary_*.json file for detailed results.
echo.
pause
