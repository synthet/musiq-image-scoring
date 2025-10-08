@echo off
REM Analyze JSON results from MUSIQ batch processing
REM Finds best and worst images overall and by each model

echo ========================================
echo    MUSIQ Results Analyzer
echo    Finding best and worst images
echo ========================================
echo.

REM Set the directory to analyze (default: current directory)
set "ANALYZE_DIR=D:\Projects\image-scoring"

REM Check if directory exists
if not exist "%ANALYZE_DIR%" (
    echo ERROR: Directory not found: %ANALYZE_DIR%
    echo.
    pause
    exit /b 1
)

echo Analyzing directory: %ANALYZE_DIR%
echo.

REM Run the analysis through WSL2
wsl bash -c "source ~/.venvs/tf/bin/activate && cd /mnt/d/Projects/image-scoring && python analyze_json_results.py --directory '%ANALYZE_DIR%'"

echo.
echo Analysis complete!
echo Check the generated analysis_summary_*.json file for detailed results.
echo.
pause
