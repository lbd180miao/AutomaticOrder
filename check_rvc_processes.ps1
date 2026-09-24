# 检查是否有其他程序占用 RVC 相机

Write-Host "🔍 检查 RVC 相关进程..." -ForegroundColor Cyan

$rvcProcesses = Get-Process | Where-Object {
    $_.ProcessName -like "*RVC*" -or
    $_.ProcessName -like "*rvc*" -or
    $_.MainWindowTitle -like "*RVC*"
}

if ($rvcProcesses.Count -eq 0) {
    Write-Host "✅ 未发现其他 RVC 进程" -ForegroundColor Green
} else {
    Write-Host "⚠️  发现以下 RVC 相关进程:" -ForegroundColor Yellow
    $rvcProcesses | Format-Table Id, ProcessName, MainWindowTitle -AutoSize
    
    Write-Host "`n❌ 这些进程可能占用相机，请手动关闭它们" -ForegroundColor Red
    Write-Host "   或运行: Stop-Process -Id <PID> -Force" -ForegroundColor Yellow
}

# 检查 Python 进程
Write-Host "`n🐍 Python 进程:" -ForegroundColor Cyan
Get-Process python -ErrorAction SilentlyContinue | Format-Table Id, StartTime, Path -AutoSize

Read-Host "`n按回车键退出"
