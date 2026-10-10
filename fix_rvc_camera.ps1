# RVC 3D相机诊断和修复脚本

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "RVC 3D相机诊断和修复" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查并关闭 RVCManager
Write-Host "[1/6] 检查 RVCManager 进程..." -ForegroundColor Yellow
$rvcManager = Get-Process -Name "RVCManager" -ErrorAction SilentlyContinue
if ($rvcManager) {
    Write-Host "  发现 RVCManager 正在运行 (PID: $($rvcManager.Id))，正在关闭..." -ForegroundColor Red
    Stop-Process -Name "RVCManager" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Host "  ✓ RVCManager 已关闭" -ForegroundColor Green
} else {
    Write-Host "  ✓ RVCManager 未运行" -ForegroundColor Green
}
Write-Host ""

# 2. 检查网卡配置
Write-Host "[2/6] 检查网卡配置..." -ForegroundColor Yellow
$adapters = Get-NetIPAddress | Where-Object { $_.IPAddress -like "169.254.*" }
if ($adapters) {
    Write-Host "  找到 169.254 网段的网卡:" -ForegroundColor Green
    foreach ($adapter in $adapters) {
        Write-Host "    - $($adapter.IPAddress) (接口: $($adapter.InterfaceAlias))" -ForegroundColor Cyan
    }
} else {
    Write-Host "  ⚠ 未找到 169.254 网段的网卡！" -ForegroundColor Red
    Write-Host "    相机IP: 169.254.10.202，需要网卡配置同网段" -ForegroundColor Yellow
}
Write-Host ""

# 3. 检查端口占用
Write-Host "[3/6] 检查端口 8001..." -ForegroundColor Yellow
$port8001 = netstat -ano | Select-String ":8001"
if ($port8001) {
    Write-Host "  端口 8001 已被占用:" -ForegroundColor Yellow
    Write-Host "  $port8001" -ForegroundColor Cyan
} else {
    Write-Host "  ✓ 端口 8001 空闲" -ForegroundColor Green
}
Write-Host ""

# 4. 检查 RVC 服务进程
Write-Host "[4/6] 检查 RVC 服务进程..." -ForegroundColor Yellow
$rvcServiceLog = "logs\rvc-service.log"
if (Test-Path $rvcServiceLog) {
    $lastLines = Get-Content $rvcServiceLog -Tail 10 | Out-String
    if ($lastLines -match "RVC 相机服务已启动") {
        Write-Host "  ✓ RVC 服务日志显示已启动" -ForegroundColor Green
    } elseif ($lastLines -match "未发现任何 RVC 设备") {
        Write-Host "  ⚠ RVC 服务启动但未找到相机设备" -ForegroundColor Red
        Write-Host "    原因: 相机未上电、网线未连接或网段不匹配" -ForegroundColor Yellow
    } else {
        Write-Host "  ? 无法确定服务状态" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ⚠ 未找到服务日志文件" -ForegroundColor Red
}
Write-Host ""

# 5. 测试服务连接
Write-Host "[5/6] 测试 RVC 服务连接..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8001/health" -TimeoutSec 3 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Host "  ✓ RVC 服务在线 (http://127.0.0.1:8001)" -ForegroundColor Green
        
        # 检查相机连接状态
        try {
            $status = Invoke-RestMethod -Uri "http://127.0.0.1:8001/status" -Method Get -ErrorAction Stop
            if ($status.data.connected) {
                Write-Host "  ✓ 相机已连接: $($status.data.device.sn) @ $($status.data.device.ip)" -ForegroundColor Green
            } else {
                Write-Host "  ⚠ 服务在线但相机未连接" -ForegroundColor Red
            }
        } catch {
            Write-Host "  ? 无法获取相机状态" -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "  ✗ RVC 服务未响应 (http://127.0.0.1:8001)" -ForegroundColor Red
    Write-Host "    错误: $($_.Exception.Message)" -ForegroundColor Yellow
}
Write-Host ""

# 6. 建议操作
Write-Host "[6/6] 诊断建议" -ForegroundColor Yellow
Write-Host ""
Write-Host "根据检查结果，建议执行以下操作:" -ForegroundColor Cyan
Write-Host ""
Write-Host "1️⃣  如果 RVCManager 仍在运行:" -ForegroundColor White
Write-Host "   手动关闭 RVCManager 程序" -ForegroundColor Gray
Write-Host ""
Write-Host "2️⃣  如果 RVC 服务未响应:" -ForegroundColor White
Write-Host "   重启 Django 服务以自动启动 RVC 服务" -ForegroundColor Gray
Write-Host "   或手动启动: python -m rvc_service" -ForegroundColor Gray
Write-Host ""
Write-Host "3️⃣  如果未找到相机设备:" -ForegroundColor White
Write-Host "   a. 检查相机电源是否打开" -ForegroundColor Gray
Write-Host "   b. 检查网线是否连接到正确网卡" -ForegroundColor Gray
Write-Host "   c. 检查网卡IP是否在 169.254.x.x 网段" -ForegroundColor Gray
Write-Host "   d. 相机IP: 169.254.10.202" -ForegroundColor Gray
Write-Host ""
Write-Host "4️⃣  修复配置文件:" -ForegroundColor White
Write-Host "   rvc_service/rvc.json 已更新为正确参数" -ForegroundColor Gray
Write-Host "   - capture_mode: 2 (Normal)" -ForegroundColor Gray
Write-Host "   - exposure_time_2d: 10ms" -ForegroundColor Gray
Write-Host "   - exposure_time_3d: 50ms" -ForegroundColor Gray
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 询问是否尝试重启服务
Write-Host "是否要尝试重启 RVC 服务? (Y/N): " -NoNewline -ForegroundColor Yellow
$answer = Read-Host
if ($answer -eq "Y" -or $answer -eq "y") {
    Write-Host ""
    Write-Host "正在尝试启动 RVC 服务..." -ForegroundColor Cyan
    Write-Host "命令: python -m rvc_service --ip 169.254.10.202" -ForegroundColor Gray
    Write-Host ""
    Write-Host "提示: 按 Ctrl+C 停止服务" -ForegroundColor Yellow
    Write-Host ""
    & python -m rvc_service --ip 169.254.10.202
}
