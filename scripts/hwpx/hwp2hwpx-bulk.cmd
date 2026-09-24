@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
python "%SCRIPT_DIR%hwp_to_hwpx_standalone.py" %* --existing-policy skip --report-json "%CD%\hwp2hwpx_bulk_report.json" --report-csv "%CD%\hwp2hwpx_bulk_report.csv"
exit /b %ERRORLEVEL%
