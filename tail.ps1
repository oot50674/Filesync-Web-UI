#Requires -Version 3.0

param(
    [string]$LogFile = "",
    [int]$TailLines = 40,
    [switch]$NoColor
)

$ErrorActionPreference = "Stop"

# 현재 스크립트 경로
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 로그 파일 경로 결정
if (!$LogFile) {
    $LogDir = Join-Path $ScriptDir "logs"
    $LatestLog = $null
    
    if (Test-Path $LogDir) {
        # 가장 최근 수정된 filesync_*.log 파일 찾기
        $LatestLog = Get-ChildItem -Path $LogDir -Filter "filesync_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    }

    if ($LatestLog) {
        $LogFile = $LatestLog.FullName
    }
    else {
        # 파일이 없으면 기본 파일명 사용
        $LogFile = Join-Path $ScriptDir "logs\filesync.log"
    }
}

# 로그 파일 존재 확인
if (!(Test-Path $LogFile)) {
    Write-Host "Log file not found. Creating new file: $LogFile" -ForegroundColor Yellow
    try {
        New-Item -ItemType File -Path $LogFile -Force | Out-Null
    }
    catch {
        Write-Host "Error creating log file: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

# 로그 파일 정보 표시
$logInfo = Get-Item $LogFile
Write-Host "=== Filesync Web UI Log Monitor ===" -ForegroundColor Cyan
Write-Host "File: $LogFile" -ForegroundColor Gray
Write-Host "Size: $([math]::Round($logInfo.Length / 1KB, 2)) KB" -ForegroundColor Gray
Write-Host "Modified: $($logInfo.LastWriteTime)" -ForegroundColor Gray
Write-Host "Showing last $TailLines lines. Press Ctrl+C to exit." -ForegroundColor Yellow
Write-Host ("=" * 50) -ForegroundColor Cyan

# 로그 파일 실시간 모니터링
try {
    Get-Content -Path $LogFile -Tail $TailLines -Wait -Encoding UTF8 | ForEach-Object {
        $line = $_

        # 색상 적용 (NoColor 옵션이 없으면)
        if (!$NoColor) {
            # 로그 레벨에 따른 색상 적용
            if ($line -match "\[ERROR\]|\[CRITICAL\]") {
                Write-Host $line -ForegroundColor Red
            }
            elseif ($line -match "\[WARNING\]") {
                Write-Host $line -ForegroundColor Yellow
            }
            elseif ($line -match "\[INFO\]") {
                Write-Host $line -ForegroundColor Green
            }
            elseif ($line -match "\[DEBUG\]") {
                Write-Host $line -ForegroundColor Gray
            }
            else {
                Write-Host $line
            }
        }
        else {
            Write-Host $line
        }
    }
}
catch [System.Management.Automation.PipelineStoppedException] {
    # Ctrl+C로 중지한 경우 - 정상 종료
    Write-Host ""
    Write-Host "Log monitoring stopped." -ForegroundColor Yellow
}
catch {
    Write-Host ""
    Write-Host "Error monitoring log file: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
