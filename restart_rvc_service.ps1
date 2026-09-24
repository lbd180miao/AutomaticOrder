# 重启 RVC 相机服务脚本
# 用法: 右键 -> 使用 PowerShell 运行

Write-Host "🔄 正在重启 RVC 相机服务..." -ForegroundColor Cyan

# 停止旧的 rvc_service 进程
$oldProcesses = Get-Process | Where-Object {
    $_.ProcessName -eq "python" -and 
    $_.Path -like "*AutomaticOrder*"
}

foreach ($proc in $oldProcesses) {
    try {
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
        if ($cmdLine -like "*rvc_service*") {
            Write-Host "   停止旧进程 (PID: $($proc.Id))..." -ForegroundColor Yellow
            Stop-Process -Id $proc.Id -Force
            Start-Sleep -Seconds 1
        }
    } catch {
        # 忽略权限错误
    }
}

Write-Host "   ✅ 旧进程已停止" -ForegroundColor Green

# 启动新进程
Write-Host "`n🚀 启动新的 RVC 服务..." -ForegroundColor Cyan

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# 激活虚拟环境并启动服务
& "$projectRoot\.venv\Scripts\python.exe" -m rvc_service

Write-Host "`n服务已启动！" -ForegroundColor Green
