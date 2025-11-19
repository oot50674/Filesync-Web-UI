@echo off
setlocal
set SCRIPT_DIR=%~dp0
set LOG_DIR=%SCRIPT_DIR%logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set LOG_FILE=%LOG_DIR%\filesync.log
echo [%date% %time%] Starting Filesync Web UI >> "%LOG_FILE%"
start "FilesyncWebUI" cmd /c "cd /d %SCRIPT_DIR% && python run.py >> \"%LOG_FILE%\" 2>&1"
echo Filesync Web UI started in background.
echo Logs: %LOG_FILE%
endlocal
