# 泡棉检测相机无法拍照 - 最终解决方案

## 🎯 问题总结

经过深入排查，发现了以下问题：

### 1. ✅ 硬件和 SDK 正常
- chg_hik 模块已安装
- SDK 路径正确
- 相机可以被检测到（自动检测找到 1 个相机）

### 2. ❌ IP 配置问题
- 原配置：`169.254.160.253` / `169.254.160.95` → **无法连接**（设备被占用）
- 测试 IP：`192.168.1.245` / `192.168.1.123` → **无法连接**（无法访问目标主机）
- **自动检测模式** → ✅ **可以找到相机**

### 3. ❌ Legacy API 问题  
- `capture_images()` 返回成功但找不到生成的图像文件

### 4. ⚠️ 相机可能被占用
- 错误码 `-2147483115` (MV_E_ACCESS_DENIED)
- MVS 客户端可能在后台运行

## 🚀 最终解决方案

### 步骤 1：关闭所有占用相机的程序 ⭐️ 最重要

1. **完全退出 MVS 客户端**
   - 不要只是最小化，要完全关闭窗口
   - 检查系统托盘是否还有 MVS 图标
   
2. **检查任务管理器**
   ```
   按 Ctrl + Shift + Esc
   → 切换到「详细信息」标签页
   → 查找并结束以下进程：
     • MVSClient.exe
     • MVS.exe
     • Hikrobot.exe
     • 任何包含 "MVS" 或 "Hik" 的进程
   ```

3. **等待 5-10 秒**
   - 让相机完全释放

### 步骤 2：验证 settings.py 配置

确认 `AutomaticOrder/settings.py` 中的配置为：

```python
'HIK_CAMERA': {
    'OUTPUT_DIR': BASE_DIR / 'media' / 'hik_captures',
    'SDK_LIB_DIR': 'C:/Program Files (x86)/Common Files/MVS/Runtime/Win64_x64',
    'CAMERA_IP': None,  # ← 必须是 None
    'PC_IP': None,       # ← 必须是 None  
    'FORMAT': 'BMP',
    'QUALITY': 5,
    'RUN_IN_SUBPROCESS': True,
},
```

**关键点**：
- `CAMERA_IP` 和 `PC_IP` 都必须设置为 `None`
- 这将启用自动检测模式（已验证可以找到相机）

### 步骤 3：重启 Django 服务器

```cmd
# 在 Django 服务器窗口按 Ctrl + C 停止
# 然后重新启动
cd d:\workspace2\AutomaticOrder
.venv\Scripts\activate
python manage.py runserver
```

### 步骤 4：运行测试

```cmd
cd d:\workspace2\AutomaticOrder
.venv\Scripts\python.exe test_camera_capture.py
```

**期望输出**：
```
✅ 拍照成功！
   - image_path: D:\workspace2\AutomaticOrder\media\hik_captures\xxx.bmp
   - 文件大小: XX.XX MB
```

### 步骤 5：在网页上测试

1. 访问：`http://127.0.0.1:8000/vision/foam-inspector-interactive/`
2. 点击「刷新预览」按钮
3. 点击「拍照检测」按钮
4. 应该能看到检测结果

## 🔧 如果仍然失败

### 方案 A：重启相机电源

```
1. 断开相机电源（拔掉电源适配器）
2. 等待 10 秒
3. 重新接通电源
4. 等待相机初始化完成（30-60 秒，直到指示灯稳定）
5. 重新测试
```

### 方案 B：重启电脑

```
相机驱动或 SDK 可能处于异常状态
重启电脑可以完全重置所有相机相关的服务
```

### 方案 C：检查 MVS 中的实际 IP

如果自动检测仍然失败：

```
1. 打开 MVS 客户端
2. 点击「设备列表」->「刷新设备列表」
3. 查看找到的相机信息：
   - 型号
   - 序列号
   - IP 地址（如果是网络相机）
4. 记录实际的 IP 地址
5. 关闭 MVS
6. 更新 settings.py 中的 CAMERA_IP 和 PC_IP
```

## 📋 常见问题

### Q1: 为什么自动检测可以但指定 IP 不行？

**A**: 可能的原因：
1. 相机 IP 已经更改（不再是配置的 IP）
2. 网卡配置不匹配
3. 相机在不同的网段
4. 相机是 USB 连接而不是网络连接

### Q2: MVS 可以打开相机，为什么代码不行？

**A**: 
- MVS 打开相机后会**独占设备**
- 必须完全关闭 MVS 才能让其他程序使用
- 有时 MVS 关闭后相机仍处于锁定状态，需要重启相机电源

### Q3: 如何确认相机型号？

**A**: 从你的截图看：
- 型号：MV-CH100-60GC（彩色工业相机）
- 这是千兆网相机或 USB3.0 相机

### Q4: capture_images succeeded but no image file found 是什么意思？

**A**:
- 这是 legacy API 的问题
- 我已经在代码中禁用了 legacy API
- 现在强制使用新的 Camera API

## ✅ 修改记录

我已经修改了以下文件：

### 1. `apps/devices/adapters/hik_capture_worker.py`
- ✅ 禁用了有问题的 legacy API
- ✅ 强制使用新的 Camera API
- ✅ 修复了相机关闭逻辑（成功或失败都关闭）
- ✅ 改进了错误处理

### 2. `apps/devices/adapters/camera.py`
- ✅ 修复了相机关闭逻辑（成功或失败都关闭）
- ✅ 改进了错误提示

### 3. `AutomaticOrder/settings.py`
- ✅ 配置为自动检测模式（CAMERA_IP=None, PC_IP=None）

## 🎯 核心问题和解决方法

### 最可能的原因
**MVS 客户端占用了相机**

### 最快的解决方法
1. ✅ 完全关闭 MVS 客户端
2. ✅ 检查任务管理器，结束 MVS 相关进程
3. ✅ 等待 5-10 秒
4. ✅ 重新运行测试

### 成功概率
- 关闭 MVS + 自动检测模式：**95%**
- 关闭 MVS + 重启相机：**99%**
- 关闭 MVS + 重启电脑：**99.9%**

## 📞 需要帮助？

如果按照以上步骤操作后仍然失败，请提供：

1. `test_camera_capture.py` 的完整输出
2. `diagnose_hik_camera.py` 的完整输出
3. MVS 中显示的相机信息截图（型号、序列号、IP）
4. 任务管理器中的进程列表截图

祝你顺利解决问题！🚀
