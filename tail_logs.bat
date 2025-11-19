@echo off
setlocal
set SCRIPT_DIR=%~dp0
set LOG_FILE=%SCRIPT_DIR%logs\filesync.log
if not exist "%LOG_FILE%" (
    echo 로그 파일을 찾을 수 없습니다: %LOG_FILE%
    exit /b 1
)
echo 최신 로그를 출력합니다. 중지하려면 Ctrl+C를 누르세요.
powershell -NoLogo -NoProfile -Command "Get-Content -Path '%LOG_FILE%' -Tail 40 -Wait"
endlocal
