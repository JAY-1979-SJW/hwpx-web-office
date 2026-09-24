@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
python "%SCRIPT_DIR%hwp_to_hwpx_standalone.py" %*
exit /b %ERRORLEVEL%
