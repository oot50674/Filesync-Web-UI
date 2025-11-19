#Requires -Version 3.0

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# 현재 스크립트 경로
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

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
    Write-Host "Python executable not found." -ForegroundColor Red
    if (!$Force) {
        Read-Host "Press Enter to exit"
    }
    exit 1
}

Write-Host "Found Python: $PythonPath" -ForegroundColor Gray

# DB 마이그레이션 실행
$runPy = Join-Path $ScriptDir "run.py"

Write-Host "Running database migration..." -ForegroundColor Yellow

try {
    # Flask 명령어 실행
    $appPath = "$runPy" + ":create_app"
    & $PythonPath -m flask --app $appPath init-db

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Migration completed successfully!" -ForegroundColor Green
        if (!$Force) {
            Read-Host "Press Enter to continue"
        }
    }
    else {
        Write-Host "Migration failed with exit code: $LASTEXITCODE" -ForegroundColor Red
        if (!$Force) {
            Read-Host "Press Enter to exit"
        }
        exit 1
    }
}
catch {
    Write-Host "Error running migration: $($_.Exception.Message)" -ForegroundColor Red
    if (!$Force) {
        Read-Host "Press Enter to exit"
    }
    exit 1
}
