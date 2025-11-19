#Requires -Version 3.0

# 콘솔 출력 인코딩을 UTF-8로 설정 (한글 깨짐 방지)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 관리자 권한 확인 및 자동 승격 (Self-elevation)
if (!([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "관리자 권한이 필요합니다. 관리자 권한으로 다시 실행합니다..." -ForegroundColor Yellow
    Start-Process powershell.exe "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`"" -Verb RunAs
    exit
}

$TaskName = "FilesyncWebUI"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ScriptDir "venv"
$PythonExe = Join-Path $VenvDir "Scripts\pythonw.exe"
$AppScript = Join-Path $ScriptDir "run.py"

# 가상환경 확인 및 자동 생성
if (!(Test-Path $PythonExe)) {
    Write-Host "가상환경을 찾을 수 없습니다. 생성 중..."
    try {
        $SysPython = Get-Command python.exe -ErrorAction Stop | Select-Object -ExpandProperty Source
        & $SysPython -m venv $VenvDir
        
        if (Test-Path $PythonExe) {
            Write-Host "가상환경이 생성되었습니다."
            $ReqFile = Join-Path $ScriptDir "requirements.txt"
            if (Test-Path $ReqFile) {
                Write-Host "의존성을 설치하는 중..."
                $VenvPython = Join-Path $VenvDir "Scripts\python.exe"
                & $VenvPython -m pip install -r $ReqFile
            }
        }
    }
    catch {
        Write-Error "가상환경 생성에 실패했습니다: $_"
        Write-Error "시스템 Python이 설치되어 있는지 확인하세요."
        exit 1
    }
}

# pythonw.exe 확인
if (-not (Test-Path $PythonExe)) {
    Write-Error "가상환경의 pythonw.exe를 찾을 수 없습니다: $PythonExe"
    exit 1
}

# pythonw.exe로 직접 실행
$Action = New-ScheduledTaskAction -Execute $PythonExe `
    -Argument "`"$AppScript`"" `
    -WorkingDirectory $ScriptDir

# 트리거 정의 (로그인 시 실행)
$Trigger = New-ScheduledTaskTrigger -AtLogon

# 설정 정의 (배터리 모드에서도 실행, 숨김 속성 등)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden -ExecutionTimeLimit (New-TimeSpan -Days 0)

# 작업 등록
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Filesync Web UI Background Service"
    Write-Host "작업이 성공적으로 등록되었습니다!" -ForegroundColor Green
    Write-Host "pythonw.exe를 사용하여 완전히 백그라운드에서 실행됩니다."
    
    # 바로 서버 시작 여부 묻기
    $startNow = Read-Host "바로 서버를 시작하시겠습니까? (Y/N)"
    if ($startNow -eq 'Y' -or $startNow -eq 'y') {
        Write-Host "서버를 시작합니다..."
        Start-Process -FilePath $PythonExe -ArgumentList "`"$AppScript`"" -WorkingDirectory $ScriptDir
        
        # 잠시 기다린 후 브라우저 열기 여부 묻기
        Start-Sleep -Seconds 3
        $openBrowser = Read-Host "브라우저에서 열어보시겠습니까? (Y/N)"
        if ($openBrowser -eq 'Y' -or $openBrowser -eq 'y') {
            Write-Host "브라우저를 엽니다..."
            Start-Process "http://127.0.0.1:5120"
        }
    }
}
catch {
    Write-Error "작업 등록 중 오류: $_"
}
