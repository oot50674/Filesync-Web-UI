#Requires -Version 3.0

param(
    [string]$ServerUrl = "http://127.0.0.1:5120",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# 서버 URL 구성
$shutdownUrl = "$ServerUrl/server/shutdown"

Write-Host "Attempting to shutdown Filesync Web UI server..." -ForegroundColor Yellow
Write-Host "Server URL: $ServerUrl" -ForegroundColor Cyan
Write-Host "Shutdown API: $shutdownUrl" -ForegroundColor Cyan

try {
    # 서버에 연결 가능한지 먼저 확인
    Write-Host "Checking server availability..." -ForegroundColor Gray
    $testResponse = Invoke-WebRequest -Uri $ServerUrl -Method GET -TimeoutSec 5
    Write-Host "Server is running (Status: $($testResponse.StatusCode))" -ForegroundColor Green

    # 사용자 확인 (Force 옵션이 없으면)
    if (!$Force) {
        $confirmation = Read-Host "Are you sure you want to shutdown the server? (y/N)"
        if ($confirmation -notmatch "^[Yy]$|^[Yy][Ee][Ss]$") {
            Write-Host "Shutdown cancelled." -ForegroundColor Yellow
            exit 0
        }
    }

    # 서버 종료 API 호출
    Write-Host "Sending shutdown request..." -ForegroundColor Yellow
    $response = Invoke-WebRequest -Uri $shutdownUrl -Method POST -TimeoutSec 10

    if ($response.StatusCode -eq 200) {
        Write-Host "Shutdown request sent successfully!" -ForegroundColor Green
        Write-Host "Response: $($response.Content)" -ForegroundColor Gray

        # 서버가 실제로 종료될 때까지 잠시 대기
        Write-Host "Waiting for server to shutdown..." -ForegroundColor Yellow
        Start-Sleep -Seconds 2

        # 서버가 종료되었는지 확인
        try {
            $finalCheck = Invoke-WebRequest -Uri $ServerUrl -Method GET -TimeoutSec 3
            Write-Host "Warning: Server may still be running (Status: $($finalCheck.StatusCode))" -ForegroundColor Yellow
        }
        catch {
            Write-Host "Server has been successfully shut down!" -ForegroundColor Green
        }
    }
    else {
        Write-Host "Unexpected response: $($response.StatusCode)" -ForegroundColor Red
        exit 1
    }

}
catch [System.Net.WebException] {
    $ex = $_.Exception
    if ($ex.Response) {
        $statusCode = [int]$ex.Response.StatusCode
        Write-Host "Server returned error: $statusCode" -ForegroundColor Red
    }
    else {
        Write-Host "Cannot connect to server. Is it running?" -ForegroundColor Red
        Write-Host "Error: $($ex.Message)" -ForegroundColor Red
    }
    exit 1
}
catch {
    Write-Host "An error occurred: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "Shutdown process completed." -ForegroundColor Green
