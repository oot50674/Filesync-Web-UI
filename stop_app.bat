@echo off
setlocal
echo Filesync Web UI 프로세스를 종료합니다.
taskkill /FI "WINDOWTITLE eq FilesyncWebUI" /T >nul 2>&1
if errorlevel 1 (
    echo 종료할 백그라운드 프로세스를 찾지 못했습니다.
    exit /b 1
)
echo 종료 명령을 전송했습니다.
endlocal
