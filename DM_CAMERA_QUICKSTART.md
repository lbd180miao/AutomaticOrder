# DM 3D深度相机快速入门指南

## 5分钟快速开始

### 步骤1: 检查安装

确保以下文件存在：
```
✓ apps/dm_camera/            # 新创建的应用
✓ C SDK DLL:                  # SDK动态库
  d:\workspace2\DM-Host-Computer-SDK\DM上位机&SDK\SDK\1.2.3\C\lib\windows\x64\dm_c_sdk.dll
✓ Python API:                 # Python绑定
  d:\workspace2\DM-Host-Computer-SDK\DM上位机&SDK\SDK\1.2.3\Python\API\zh\
```

### 步骤2: 连接硬件

1. 将DM 3D深度相机通过网线连接到电脑
2. 确保相机已通电
3. 配置网络（相机和电脑需在同一网段）

### 步骤3: 运行数据库迁移（已完成）

```bash
python manage.py makemigrations dm_camera
python manage.py migrate
```

### 步骤4: 启动Django服务器

```bash
python manage.py runserver
```

### 步骤5: 测试相机连接

#### 方法A: 使用Python测试脚本

```bash
# 测试查找设备
python test_dm_camera.py --test find

# 运行完整测试
python test_dm_camera.py
```

#### 方法B: 使用REST API测试客户端

```bash
# 确保Django服务器在运行，然后在另一个终端执行：
python test_dm_camera_api.py
```

#### 方法C: 使用curl测试API

```bash
# 查找设备
curl http://localhost:8000/dm-camera/api/devices/find/

# 连接设备
curl -X POST http://localhost:8000/dm-camera/api/connect/ -H "Content-Type: application/json"

# 获取状态
curl http://localhost:8000/dm-camera/api/status/
```

### 步骤6: 在Django Admin中查看

1. 创建超级用户（如果还没有）：
```bash
python manage.py createsuperuser
```

2. 访问Admin界面：
```
http://localhost:8000/admin/
```

3. 查看以下内容：
- DM相机配置 (DM Camera Configs)
- DM采集记录 (DM Capture Records)
- DM相机会话 (DM Camera Sessions)

## 常用操作示例

### 在Python代码中使用

```python
from apps.dm_camera.services import DMCameraService

# 初始化服务
service = DMCameraService()

# 连接设备
service.connect()

# 开启数据流
service.start_stream()

# 捕获深度图
result = service.capture(frame_type='DEPTH', save_record=True)
print(f"捕获成功，预览图: {result['preview_url']}")

# 停止数据流
service.stop_stream()

# 断开连接
service.disconnect()
```

### 通过REST API使用

```python
import requests

BASE_URL = "http://localhost:8000/dm-camera/api"

# 连接设备
response = requests.post(f"{BASE_URL}/connect/")
print(response.json())

# 开启数据流
response = requests.post(f"{BASE_URL}/stream/start/")

# 捕获一帧
response = requests.post(f"{BASE_URL}/capture/", json={
    "frame_type": "DEPTH",
    "save_record": True
})
result = response.json()
print(f"预览图: {result['data']['preview_url']}")

# 停止数据流
requests.post(f"{BASE_URL}/stream/stop/")

# 断开连接
requests.post(f"{BASE_URL}/disconnect/")
```

### JavaScript前端集成

```javascript
// 连接并捕获
async function captureDepthImage() {
    // 连接设备
    await fetch('/dm-camera/api/connect/', { method: 'POST' });
    
    // 开启数据流
    await fetch('/dm-camera/api/stream/start/', { method: 'POST' });
    
    // 捕获深度图
    const response = await fetch('/dm-camera/api/capture/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frame_type: 'DEPTH', save_record: true })
    });
    
    const data = await response.json();
    
    // 显示预览图
    document.getElementById('preview').src = data.data.preview_url;
    
    // 停止数据流
    await fetch('/dm-camera/api/stream/stop/', { method: 'POST' });
    
    // 断开连接
    await fetch('/dm-camera/api/disconnect/', { method: 'POST' });
}
```

## API端点速查

### 设备控制
- `GET  /dm-camera/api/devices/find/` - 查找设备
- `POST /dm-camera/api/connect/` - 连接设备
- `POST /dm-camera/api/disconnect/` - 断开设备
- `GET  /dm-camera/api/status/` - 获取状态

### 数据流
- `POST /dm-camera/api/stream/start/` - 开启数据流
- `POST /dm-camera/api/stream/stop/` - 停止数据流
- `POST /dm-camera/api/capture/` - 捕获一帧

### 配置管理
- `GET  /dm-camera/api/configs/` - 列出配置
- `POST /dm-camera/api/configs/create/` - 创建配置
- `GET  /dm-camera/api/configs/{id}/` - 获取配置
- `PUT  /dm-camera/api/configs/{id}/update/` - 更新配置
- `DELETE /dm-camera/api/configs/{id}/delete/` - 删除配置

### 采集记录
- `GET /dm-camera/api/captures/` - 列出记录
- `GET /dm-camera/api/captures/{id}/` - 获取记录详情

## 配置参数说明

### 采集参数
- **帧率** (frame_rate): 1-30 fps，建议10-15
- **曝光时间** (exposure_time): 微秒，范围根据帧率而定，建议500-1500
- **触发模式** (trigger_mode):
  - `ACTIVE`: 主动模式（连续采集）
  - `SOFT`: 软触发（API控制）
  - `HARD`: 硬触发（外部信号）

### 滤波参数
- **置信度滤波** (confidence_threshold): 1-150，建议15-20
- **飞点滤波** (flying_pixels_threshold): 1-64，建议5-10
- **空间滤波** (spatial_threshold): 3, 5, 7，建议5

## 数据类型说明

### 帧类型
- `DEPTH`: 深度图（单位：毫米）
- `IR`: 红外图
- `POINTCLOUD`: 点云数据

### 数据格式
- 深度图/IR图: numpy数组 (height, width)，uint16
- 点云: numpy数组 (height*width, 3)，float32 (x, y, z)

## 故障排查

### 问题1: 找不到设备
```bash
# 检查网络连接
ping 192.168.1.100  # 替换为你的相机IP

# 检查SDK是否正确加载
python test_dm_camera.py --test find
```

### 问题2: 连接超时
- 检查防火墙设置
- 确认相机IP配置
- 增加超时时间

### 问题3: 捕获失败
- 确保数据流已开启
- 检查曝光时间和帧率配置
- 查看温度是否过高

## 性能建议

1. **网络优化**: 使用千兆以太网，避免WiFi
2. **帧率设置**: 根据应用场景选择合适帧率，避免过高
3. **批量采集**: 一次连接采集多帧，减少连接开销
4. **异步处理**: 对于实时应用，考虑使用异步任务队列
5. **资源释放**: 及时断开连接，释放相机资源

## 下一步

- 查看完整文档: [DM_CAMERA_README.md](DM_CAMERA_README.md)
- 浏览代码示例: `test_dm_camera.py`, `test_dm_camera_api.py`
- 集成到你的应用: 参考 `apps/dm_camera/services.py`
- 自定义前端: 使用提供的REST API

## 技术支持

如遇问题，请查看：
1. SDK文档: `DM-Host-Computer-SDK/DM上位机&SDK/SDK/1.2.3/C/doc/zh/`
2. 日志文件: Django日志中的dm_camera相关信息
3. 测试脚本: `test_dm_camera.py --test <test_name>`
