"""
RVC 相机快速连接验证脚本（基于官方 SDK 示例）
在项目根目录运行：python test_rvc_connect.py
运行前：1) 关闭 RVCManager  2) 确认网卡 IP 在 169.254.x.x 网段
"""
import sys

try:
    import PyRVC as RVC
except ImportError:
    print("❌ PyRVC 未安装！请执行: pip install PyRVC")
    sys.exit(1)

print("=" * 60)
print("RVC 相机连接验证脚本")
print("=" * 60)

# Step 1: 初始化
print("\n[1] 初始化 RVC SDK ...")
ok = RVC.SystemInit()
print(f"  SystemInit: {'✅ OK' if ok else '❌ 失败'}")

# Step 2: 枚举设备
print("\n[2] 扫描设备 ...")
ret, devices = RVC.SystemListDevices(RVC.SystemListDeviceTypeEnum.All)
print(f"  发现设备数量: {len(devices)}")

if len(devices) == 0:
    print("  ❌ 未发现任何 RVC 设备！")
    print("  检查：")
    print("    1. 相机已上电")
    print("    2. 网卡 IP 设为 169.254.10.xxx，子网掩码 255.255.0.0")
    print("    3. 已关闭 RVCManager")
    RVC.SystemShutdown()
    sys.exit(1)

# Step 3: 打印设备信息
print("\n[3] 设备列表：")
for i, dev in enumerate(devices):
    ret_info, info = dev.GetDeviceInfo()
    fw_ok = dev.IsFirmwareMatch()
    print(f"  设备[{i}]: SN={info.sn}  名称={info.name}  固件匹配={fw_ok}")
    print(f"           X1支持={info.support_x1}  X2支持={info.support_x2}  彩色={info.support_color}")

device = devices[0]
ret_info, info = device.GetDeviceInfo()

if not device.IsFirmwareMatch():
    print("\n  ⚠️  固件版本不匹配，请用 RVCManager 升级固件后再试")

# Step 4: 打开相机
print(f"\n[4] 打开相机（SN={info.sn}）...")
if info.support_x2:
    print("  → 使用 X2 模式")
    cam = RVC.X2.Create(device)
    cam_type = "X2"
else:
    print("  → 使用 X1 模式")
    cam = RVC.X1.Create(device, RVC.CameraID_Left)
    cam_type = "X1"

opened = cam.Open()
if not cam.IsOpen():
    msg = RVC.GetLastErrorMessage()
    print(f"  ❌ 打开失败: {msg}")
    if cam_type == "X2":
        RVC.X2.Destroy(cam)
    else:
        RVC.X1.Destroy(cam)
    RVC.SystemShutdown()
    sys.exit(1)

print("  ✅ 相机已打开！")

# Step 5: 读取曝光范围
try:
    _, exp_min, exp_max = cam.GetExposureTimeRange()
    print(f"\n[5] 曝光时间范围: [{exp_min}, {exp_max}] µs")
except Exception as e:
    print(f"\n[5] 读取曝光范围失败: {e}")

# Step 6: 采集测试
print("\n[6] 执行采集（Method 3：直接使用相机内部参数）...")
ok = cam.Capture()
if ok:
    print("  ✅ 采集成功！")
    pm = cam.GetPointMap()
    if pm and pm.IsValid():
        size = pm.GetSize()
        import numpy as np
        pm_np = np.array(pm, copy=False).reshape(-1, 3)
        valid = int((~np.isnan(pm_np).any(axis=1)).sum())
        print(f"  点云尺寸: {size.width}x{size.height}  有效点: {valid}")
    else:
        print("  ⚠️  点云无效（检查曝光/被测物距离）")
else:
    msg = RVC.GetLastErrorMessage()
    print(f"  ❌ 采集失败: {msg}")

# Step 7: 关闭
print("\n[7] 释放资源 ...")
cam.Close()
if cam_type == "X2":
    RVC.X2.Destroy(cam)
else:
    RVC.X1.Destroy(cam)
RVC.SystemShutdown()
print("  ✅ 完成")
print("\n" + "=" * 60)
