#Requires -Version 3.0

# 콘솔 출력 인코딩을 UTF-8로 설정
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 관리자 권한 확인 및 자동 승격
if (!([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "관리자 권한이 필요합니다. 관리자 권한으로 다시 실행합니다..." -ForegroundColor Yellow
    Start-Process powershell.exe "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`"" -Verb RunAs
    exit
}

$TaskName = "FilesyncWebUI"

try {
    # 작업 존재 여부 확인
    $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    
    if ($Task) {
        # 작업 삭제
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "작업 스케줄러에서 '$TaskName' 작업이 성공적으로 제거되었습니다." -ForegroundColor Green
    }
    else {
        Write-Host "작업 스케줄러에 '$TaskName' 작업이 존재하지 않습니다." -ForegroundColor Yellow
    }
}
catch {
    Write-Error "작업 제거 중 오류가 발생했습니다: $_"
}
