#Requires -Version 3.0

param(
    [switch]$Console
)

$ErrorActionPreference = "Stop"

# 현재 스크립트 경로
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogFile = Join-Path $ScriptDir "logs\filesync.log"

# 로그 디렉토리 생성
$LogDir = Join-Path $ScriptDir "logs"
if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# Python 실행 파일 찾기
$PythonPath = $null

# 1. venv 확인
$VenvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonPath = $VenvPython
}

# 2. 시스템 PATH 확인
if (!$PythonPath) {
    try {
        $PythonPath = Get-Command python.exe -ErrorAction Stop | Select-Object -ExpandProperty Source
    }
    catch {
        $PythonPath = $null
    }
}

# 3. 찾지 못한 경우
if (!$PythonPath) {
    $ErrorMsg = "[$(Get-Date)] Error: Python not found."
    Write-Host $ErrorMsg -ForegroundColor Red
    Add-Content -Path $LogFile -Value $ErrorMsg
    if (!$Console) {
        Read-Host "Press Enter to exit"
    }
    exit 1
}

# 실행 정보 기록
$StartMsg = "[$(Get-Date)] Starting Filesync Web UI..."
Add-Content -Path $LogFile -Value $StartMsg
Write-Host "Selected Python: $PythonPath"

# 서버 실행 명령어
$RunPy = Join-Path $ScriptDir "run.py"
$Command = "`"$PythonPath`" `"$RunPy`""

# 로그 리다이렉션 포함
$FullCommand = "cmd /c `"$Command >> `"$LogFile`" 2>&1`""

# 콘솔 모드 vs 백그라운드 모드
if ($Console) {
    # 콘솔 모드: 창 유지
    Write-Host "Running in console mode. Press Ctrl+C to stop."
    Invoke-Expression $FullCommand
}
else {
    # 백그라운드 모드: 창 없이 실행
    try {
        Start-Process -FilePath "cmd" -ArgumentList "/c `"$FullCommand`"" -NoNewWindow -Wait:$false
        Write-Host "Filesync Web UI started in background."
        Write-Host "Logs: $LogFile"
    }
    catch {
        $ErrorMsg = "[$(Get-Date)] Failed to start process: $($_.Exception.Message)"
        Write-Host $ErrorMsg -ForegroundColor Red
        Add-Content -Path $LogFile -Value $ErrorMsg
        Read-Host "Press Enter to exit"
        exit 1
    }
}

