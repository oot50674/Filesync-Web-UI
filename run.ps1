#Requires -Version 3.0

$ErrorActionPreference = "Stop"

# 현재 스크립트 경로
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Python 실행 파일 찾기
$PythonPath = $null

# 1. venv 확인 및 자동 생성
$VenvDir = Join-Path $ScriptDir "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (!(Test-Path $VenvPython)) {
    Write-Host "Virtual environment not found. Creating..."
    try {
        $SysPython = Get-Command python.exe -ErrorAction Stop | Select-Object -ExpandProperty Source
        & $SysPython -m venv $VenvDir
        
        if (Test-Path $VenvPython) {
            Write-Host "Virtual environment created."
            $ReqFile = Join-Path $ScriptDir "requirements.txt"
            if (Test-Path $ReqFile) {
                Write-Host "Installing dependencies..."
                & $VenvPython -m pip install -r $ReqFile
            }
        }
    }
    catch {
        Write-Host "Warning: Failed to create venv. Using system Python if available." -ForegroundColor Yellow
    }
}

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
    if (!$Console) {
        Read-Host "Press Enter to exit"
    }
    exit 1
}

# 실행 정보 기록
$StartMsg = "[$(Get-Date)] Starting Filesync Web UI..."
Write-Host $StartMsg
Write-Host "Selected Python: $PythonPath"
Write-Host "Log file: will be created by Flask (run.py)"

# 서버 실행 명령어
$RunPy = Join-Path $ScriptDir "run.py"
# 명령: Python 실행 경로와 대상 스크립트

# 백그라운드에서 실행
$Pythonw = Join-Path $VenvDir "Scripts\pythonw.exe"
if (Test-Path $Pythonw) {
    Write-Host "Starting Flask with pythonw.exe (no console)."
    $proc = Start-Process -FilePath $Pythonw -ArgumentList "`"$RunPy`"" -WorkingDirectory $ScriptDir -WindowStyle Hidden -PassThru
}
else {
    Write-Host "Starting Flask as detached process (python.exe)."
    $proc = Start-Process -FilePath $PythonPath -ArgumentList "`"$RunPy`"" -WorkingDirectory $ScriptDir -WindowStyle Hidden -PassThru
}

if ($proc) {
    Write-Host "Flask started (PID: $($proc.Id)). The server will continue running after this window is closed."
}
else {
    Write-Host "Failed to start Flask as detached process; attempting to run in foreground..." -ForegroundColor Yellow
    & "$PythonPath" "$RunPy"
}

