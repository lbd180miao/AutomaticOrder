# DM 3D深度相机集成文档

## 概述

本模块将DM 3D深度相机SDK集成到Django项目中，提供REST API和后端服务，用于控制相机、采集深度数据和管理配置。

## 架构设计

```
apps/dm_camera/
├── sdk_wrapper.py      # SDK包装层（ctypes调用C DLL）
├── services.py         # 业务逻辑服务层（单例模式）
├── views.py           # REST API视图
├── models.py          # 数据模型（配置、记录、会话）
├── urls.py            # URL路由
└── admin.py           # Django Admin配置
```

### 技术栈

- **Python绑定层**: ctypes调用C SDK的DLL
- **Django 4.2+**: Web框架
- **REST API**: Django视图函数
- **数据存储**: SQLite（相机配置、历史记录）
- **依赖库**: numpy, Pillow

## 安装配置

### 1. 运行数据库迁移

```bash
python manage.py makemigrations dm_camera
python manage.py migrate
```

### 2. 创建媒体目录

```bash
mkdir media\dm_camera\captures
mkdir media\dm_camera\previews
```

### 3. 检查SDK路径

确保SDK DLL文件存在于正确位置：
```
d:\workspace2\DM-Host-Computer-SDK\DM上位机&SDK\SDK\1.2.3\C\lib\windows\x64\dm_c_sdk.dll
```

## REST API使用指南

### 基础URL

所有API的基础URL为：`http://localhost:8000/dm-camera/api/`

### 1. 设备管理

#### 查找设备
```http
GET /dm-camera/api/devices/find/
```

响应示例：
```json
{
    "success": true,
    "data": {
        "devices": [
            {
                "handle": 12345678,
                "sn": "DM02C12345678",
                "type": "LWP-DM02C",
                "ip": "192.168.1.100",
                "local_ip": "192.168.1.10"
            }
        ]
    }
}
```

#### 连接设备
```http
POST /dm-camera/api/connect/
Content-Type: application/json

{
    "device_sn": "DM02C12345678",  // 可选，不指定则连接第一个设备
    "config_id": 1                 // 可选，不指定则使用激活的配置
}
```

响应示例：
```json
{
    "success": true,
    "data": {
        "device_sn": "DM02C12345678",
        "device_type": "LWP-DM02C",
        "device_ip": "192.168.1.100",
        "config_name": "默认配置",
        "session_id": 1
    }
}
```

#### 断开设备
```http
POST /dm-camera/api/disconnect/
```

#### 获取状态
```http
GET /dm-camera/api/status/
```

响应示例：
```json
{
    "success": true,
    "data": {
        "connected": true,
        "streaming": true,
        "session": {
            "id": 1,
            "device_sn": "DM02C12345678",
            "device_ip": "192.168.1.100",
            "status": "STREAMING",
            "config_name": "默认配置"
        },
        "device_info": {
            "sn": "DM02C12345678",
            "frame_rate": 10,
            "trigger_mode": "LW_TRIGGER_ACTIVE",
            "resolution": "640x480",
            "is_streaming": true
        }
    }
}
```

### 2. 数据流控制

#### 开启数据流
```http
POST /dm-camera/api/stream/start/
```

#### 停止数据流
```http
POST /dm-camera/api/stream/stop/
```

#### 捕获一帧
```http
POST /dm-camera/api/capture/
Content-Type: application/json

{
    "frame_type": "DEPTH",     // DEPTH, IR, POINTCLOUD
    "save_record": true        // 是否保存到数据库
}
```

响应示例：
```json
{
    "success": true,
    "data": {
        "frame_type": "DEPTH",
        "width": 640,
        "height": 480,
        "frame_index": 42,
        "timestamp": {
            "sec": 1234567890,
            "usec": 123456
        },
        "temperature": {
            "chip": 45.5,
            "laser1": 42.3,
            "laser2": 43.1
        },
        "record_id": 100,
        "preview_url": "/media/dm_camera/previews/2024/01/15/DEPTH_42_20240115_123456.png"
    }
}
```

### 3. 配置管理

#### 列出所有配置
```http
GET /dm-camera/api/configs/
```

#### 获取配置详情
```http
GET /dm-camera/api/configs/1/
```

#### 创建配置
```http
POST /dm-camera/api/configs/create/
Content-Type: application/json

{
    "name": "高帧率配置",
    "device_sn": "",
    "frame_rate": 20,
    "exposure_time": 500,
    "trigger_mode": "ACTIVE",
    "confidence_filter_enable": true,
    "confidence_threshold": 15,
    "flying_pixels_filter_enable": true,
    "flying_pixels_threshold": 5,
    "spatial_filter_enable": true,
    "spatial_threshold": 5,
    "is_active": false
}
```

#### 更新配置
```http
PUT /dm-camera/api/configs/1/update/
Content-Type: application/json

{
    "frame_rate": 15,
    "exposure_time": 800
}
```

#### 删除配置
```http
DELETE /dm-camera/api/configs/1/delete/
```

### 4. 采集记录

#### 列出采集记录
```http
GET /dm-camera/api/captures/?page=1&page_size=20&frame_type=DEPTH
```

#### 获取采集记录详情
```http
GET /dm-camera/api/captures/100/
```

## Python使用示例

### 基础使用

```python
from apps.dm_camera.services import DMCameraService
from apps.dm_camera.sdk_wrapper import DMCameraException

# 获取服务实例（单例）
service = DMCameraService()

try:
    # 1. 查找设备
    devices = service.find_devices()
    print(f"找到 {len(devices)} 个设备")
    
    # 2. 连接设备（连接第一个设备）
    result = service.connect()
    print(f"已连接: {result['device_sn']}")
    
    # 3. 开启数据流
    service.start_stream()
    print("数据流已开启")
    
    # 4. 捕获深度图
    frame_data = service.capture(frame_type='DEPTH', save_record=True)
    print(f"捕获帧 #{frame_data['frame_index']}")
    print(f"分辨率: {frame_data['width']}x{frame_data['height']}")
    print(f"温度: {frame_data['temperature']['chip']}°C")
    
    # 5. 捕获IR图
    ir_data = service.capture(frame_type='IR', save_record=True)
    print(f"IR帧预览: {ir_data['preview_url']}")
    
    # 6. 停止数据流
    service.stop_stream()
    
    # 7. 断开连接
    service.disconnect()
    print("已断开连接")
    
except DMCameraException as e:
    print(f"错误: {e}")
```

### 使用上下文管理器

```python
from apps.dm_camera.sdk_wrapper import DMCamera, LWFrameType

# 使用上下文管理器自动管理连接
with DMCamera() as camera:
    # 查找并连接第一个设备
    devices = camera.find_devices()
    device_info = camera.connect(devices[0])
    
    # 配置相机
    camera.configure_camera(
        frame_rate=15,
        exposure_time=800
    )
    
    # 配置滤波器
    camera.set_filters(
        confidence=(True, 20),
        flying_pixels=(True, 8),
        spatial=(True, 7)
    )
    
    # 开启数据流并捕获
    camera.start_stream()
    
    for i in range(10):
        frame = camera.capture_frame(LWFrameType.LW_DEPTH_FRAME)
        print(f"帧 {i}: {frame.width}x{frame.height}")
    
    camera.stop_stream()
    # 自动断开连接
```

### 批量采集

```python
import time
from apps.dm_camera.services import DMCameraService

service = DMCameraService()

def batch_capture(count=100, interval=0.1):
    """批量采集深度图"""
    try:
        service.connect()
        service.start_stream()
        
        captures = []
        for i in range(count):
            result = service.capture(frame_type='DEPTH', save_record=True)
            captures.append(result)
            print(f"已采集 {i+1}/{count}")
            time.sleep(interval)
        
        service.stop_stream()
        service.disconnect()
        
        return captures
    
    except Exception as e:
        print(f"批量采集失败: {e}")
        service.disconnect()
        return []

# 执行批量采集
results = batch_capture(count=50, interval=0.05)
print(f"总计采集 {len(results)} 帧")
```

## 前端集成示例（JavaScript）

```javascript
// DM相机API客户端
class DMCameraAPI {
    constructor(baseURL = '/dm-camera/api') {
        this.baseURL = baseURL;
    }
    
    async request(endpoint, options = {}) {
        const response = await fetch(`${this.baseURL}${endpoint}`, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
        });
        
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error);
        }
        return data.data;
    }
    
    // 查找设备
    async findDevices() {
        return await this.request('/devices/find/');
    }
    
    // 连接设备
    async connect(deviceSN = null, configID = null) {
        return await this.request('/connect/', {
            method: 'POST',
            body: JSON.stringify({ device_sn: deviceSN, config_id: configID }),
        });
    }
    
    // 断开连接
    async disconnect() {
        return await this.request('/disconnect/', { method: 'POST' });
    }
    
    // 获取状态
    async getStatus() {
        return await this.request('/status/');
    }
    
    // 开启数据流
    async startStream() {
        return await this.request('/stream/start/', { method: 'POST' });
    }
    
    // 停止数据流
    async stopStream() {
        return await this.request('/stream/stop/', { method: 'POST' });
    }
    
    // 捕获一帧
    async capture(frameType = 'DEPTH', saveRecord = true) {
        return await this.request('/capture/', {
            method: 'POST',
            body: JSON.stringify({ frame_type: frameType, save_record: saveRecord }),
        });
    }
    
    // 获取采集记录列表
    async getCaptureList(page = 1, pageSize = 20, frameType = null) {
        const params = new URLSearchParams({ page, page_size: pageSize });
        if (frameType) params.append('frame_type', frameType);
        return await this.request(`/captures/?${params}`);
    }
}

// 使用示例
const dmCamera = new DMCameraAPI();

async function captureDepthImage() {
    try {
        // 连接设备
        await dmCamera.connect();
        
        // 开启数据流
        await dmCamera.startStream();
        
        // 捕获深度图
        const result = await dmCamera.capture('DEPTH', true);
        
        // 显示预览图
        document.getElementById('preview').src = result.preview_url;
        
        console.log('捕获成功:', result);
    } catch (error) {
        console.error('捕获失败:', error);
    }
}
```

## 数据模型

### DMCameraConfig（相机配置）
- 存储相机采集参数和滤波器配置
- 支持多配置切换
- 一次只能有一个激活配置

### DMCaptureRecord（采集记录）
- 存储每次采集的元数据
- 包含预览图和原始数据文件路径
- 记录温度、时间戳等信息

### DMCameraSession（会话）
- 跟踪设备连接状态
- 记录错误信息
- 关联使用的配置

## 常见问题

### 1. DLL加载失败

**问题**: `Unable to load dynamic libraries for Windows`

**解决方案**:
- 确认DLL文件路径正确
- 检查Python架构（32位/64位）与DLL匹配
- 确保Visual C++ Redistributable已安装

### 2. 设备未找到

**问题**: `未找到可用设备`

**解决方案**:
- 确认设备已开机并连接到网络
- 检查网络配置（IP地址、子网掩码）
- 使用SDK自带工具测试设备连通性

### 3. 捕获超时

**问题**: `获取帧准备失败`

**解决方案**:
- 检查曝光时间和帧率配置是否合理
- 确保数据流已正确开启
- 增加超时时间配置

### 4. 温度过高

**问题**: 芯片温度超过阈值

**解决方案**:
- 降低帧率
- 减少曝光时间
- 改善散热条件

## 性能优化建议

1. **批量采集**: 使用单次连接采集多帧数据，避免频繁连接断开
2. **异步处理**: 对于耗时的数据处理，使用异步任务队列
3. **缓存管理**: 定期清理旧的采集记录和文件
4. **网络优化**: 确保相机和主机在同一局域网内
5. **资源释放**: 使用完毕后及时断开连接，释放资源

## 未来扩展

- [ ] WebSocket实时数据流推送
- [ ] 点云数据3D可视化
- [ ] 多相机同步采集
- [ ] 自动标定功能
- [ ] 数据导出功能（PCD、PLY格式）
- [ ] 集成深度学习算法

## 技术支持

如有问题，请联系开发团队或查阅SDK官方文档。
