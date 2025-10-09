@echo off
REM Wrapper script for backward compatibility
REM Calls the actual script in scripts/batch/

"%~dp0scripts\batch\create_gallery.bat" %*

