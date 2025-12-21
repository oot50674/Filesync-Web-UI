#Requires -Version 3.0

# 콘솔 출력 인코딩을 UTF-8로 설정합니다.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 관리자 권한 실행 여부 확인 및 자동 승격 처리
if (!([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "관리자 권한이 필요합니다. 관리자 권한으로 다시 실행합니다..." -ForegroundColor Yellow
    Start-Process powershell.exe "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`"" -Verb RunAs
    exit
}

$TaskName = "FilesyncWebUI"

try {
    # 작업 스케줄러에 해당 작업이 존재하는지 확인합니다.
    $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    
    if ($Task) {
        # 작업을 등록 해제합니다.
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "작업 스케줄러에서 '$TaskName' 작업이 성공적으로 삭제되었습니다." -ForegroundColor Green
    }
    else {
        Write-Host "작업 스케줄러에 '$TaskName' 작업이 존재하지 않습니다." -ForegroundColor Yellow
    }
}
catch {
    Write-Error "작업 삭제 중 오류가 발생했습니다: $_"
}
