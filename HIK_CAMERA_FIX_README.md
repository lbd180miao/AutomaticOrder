# 海康威视相机错误修复指南

## 问题描述
错误信息: `图像采集失败: 相机 0 保存图像失败，错误码: -2147483646`

错误码 `-2147483646` (十六进制: `0x80000002`) 是海康威视SDK返回的保存图像失败错误。

## 已应用的修复

### 1. 增强目录权限检查
**修改文件**: 
- `apps/devices/adapters/camera.py`
- `apps/devices/adapters/hik_capture_worker.py`

**修改内容**:
- 添加输出目录创建时的异常处理
- 添加写入权限测试
- 提供更详细的错误信息

### 2. 修改图像格式配置
**修改文件**: `AutomaticOrder/settings.py`

**修改内容**:
```python
'FORMAT': 'BMP',  # 从 PNG 改为 BMP
```

**原因**: BMP格式是未压缩格式，不需要额外的编码处理，可以避免某些SDK版本的兼容性问题。

### 3. 添加诊断工具
**新增文件**: `diagnose_hik_camera.py`

这是一个综合诊断工具，可以检查所有可能导致错误的配置问题。

## 使用诊断工具

运行诊断脚本：
```bash
python diagnose_hik_camera.py
```

诊断工具会检查：
1. ✓ 输出目录是否存在且可写
2. ✓ SDK库文件是否完整
3. ✓ Python绑定模块是否正确安装
4. ✓ 网络配置是否正确
5. ✓ 图像格式配置是否有效

## 手动排查步骤

### 步骤 1: 检查输出目录
```bash
# 确保目录存在
mkdir -p d:/workspace2/AutomaticOrder/media/hik_captures

# 检查权限（Windows PowerShell）
Get-Acl d:/workspace2/AutomaticOrder/media/hik_captures
```

### 步骤 2: 验证磁盘空间
确保至少有 1GB 可用空间。

### 步骤 3: 测试SDK安装
使用海康威视官方客户端 MVS (Machine Vision Software) 测试相机是否正常工作。

### 步骤 4: 检查网络连接
```bash
# Ping 相机IP
ping 169.254.160.253

# 检查本机IP配置
ipconfig
```

确认本机有 `169.254.160.95` 这个IP地址。

### 步骤 5: 尝试不同的格式
如果 BMP 仍然失败，在 `settings.py` 中尝试：
```python
'FORMAT': 'JPEG',  # 或 'JPG'
'QUALITY': 5,
```

## 其他可能的解决方案

### 方案 1: 使用相对路径而非绝对路径
某些SDK版本对长路径支持不佳，可以尝试使用较短的路径：
```python
'OUTPUT_DIR': Path('C:/hik_temp'),
```

### 方案 2: 检查防火墙
确保Windows防火墙允许GigE Vision协议（端口3956）。

### 方案 3: 更新SDK版本
如果使用的SDK版本过旧，考虑更新到最新版本。

当前配置的SDK路径：
```
C:/Program Files (x86)/Common Files/MVS/Runtime/Win64_x64
```

### 方案 4: 调整相机参数
在代码中可以尝试调整：
```python
'QUALITY': 3,  # 降低质量参数
```

### 方案 5: 禁用子进程模式
在 `settings.py` 中添加：
```python
'RUN_IN_SUBPROCESS': False,
```

这会在主进程中直接调用相机，有助于诊断问题。

## 测试修复

1. 运行诊断工具：
```bash
python diagnose_hik_camera.py
```

2. 重启Django服务器：
```bash
python manage.py runserver
```

3. 访问视觉任务页面测试：
```
http://127.0.0.1:8000/vision/tasks/
```

4. 触发相机拍照任务，查看是否还有错误。

## 日志查看

检查Django日志输出，查找更详细的错误信息：
```bash
# 查看完整的错误堆栈
```

## 联系支持

如果问题仍未解决，收集以下信息：
1. 诊断工具的完整输出
2. Django服务器的完整错误日志
3. MVS客户端的测试结果
4. 相机型号和固件版本
5. SDK版本信息

## 参考资料

- [海康威视MVS SDK文档](https://www.hikrobotics.com/cn/machinevision/service/download)
- SDK错误码参考：`MvErrorDefine.h`
- 常见错误码含义：
  - `0x80000002`: 保存图像失败（文件路径、权限或格式问题）
  - `0x80000007`: 参数错误
  - `0x80000001`: 通用错误
