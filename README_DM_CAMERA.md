# DM 3D深度相机 Django集成

## 🎯 项目概述

本项目将**DM 3D深度相机SDK**完整集成到Django项目中，提供：

- ✅ **REST API接口** - 标准HTTP API，支持所有主要功能
- ✅ **Python服务层** - 易用的Python服务类
- ✅ **数据持久化** - SQLite存储配置和采集记录
- ✅ **Web管理界面** - Django Admin后台管理
- ✅ **演示页面** - 完整的Web UI演示
- ✅ **完善文档** - 详细的使用文档和测试脚本

## 🚀 5分钟快速开始

### 方式1: 使用启动脚本（推荐）

```bash
# Windows
start_dm_camera_demo.bat

# 自动完成检查、迁移和启动服务
```

### 方式2: 手动启动

```bash
# 1. 检查集成
python check_dm_camera_setup.py

# 2. 启动服务
python manage.py runserver

# 3. 访问演示页面
# 浏览器打开: http://localhost:8000/dm-camera/
```

## 📚 文档导航

| 文档 | 说明 | 适合人群 |
|------|------|----------|
| [DM_CAMERA_QUICKSTART.md](DM_CAMERA_QUICKSTART.md) | 5分钟快速入门指南 | 🔰 新手 |
| [DM_CAMERA_README.md](DM_CAMERA_README.md) | 完整技术文档和API参考 | 👨‍💻 开发者 |
| [DM_CAMERA_INTEGRATION_SUMMARY.md](DM_CAMERA_INTEGRATION_SUMMARY.md) | 集成架构和技术总结 | 🏗️ 架构师 |
| [DEPLOYMENT_GUIDE_DM_CAMERA.md](DEPLOYMENT_GUIDE_DM_CAMERA.md) | 部署指南和故障排查 | 🔧 运维 |

## 🔧 主要功能

### 设备管理
- 自动发现网络中的DM相机
- 连接/断开设备
- 实时状态监控
- 设备信息查询

### 数据采集
- 深度图采集
- IR图采集
- 点云数据采集
- 批量采集支持
- 实时预览图生成

### 配置管理
- 多配置存储和切换
- 帧率、曝光时间配置
- 滤波器参数配置
- 触发模式配置

### 数据管理
- 采集记录自动保存
- 预览图和原始数据存储
- 分页查询支持
- 温度和时间戳记录

## 🎨 界面预览

### Web演示页面
访问 `http://localhost:8000/dm-camera/` 查看完整功能演示：

- 🔍 设备查找和连接
- ▶️ 数据流控制
- 📸 实时图像采集
- 📊 采集信息显示
- 📝 操作日志

### Django Admin
访问 `http://localhost:8000/admin/` 管理后台：

- 📋 配置管理
- 📁 采集记录查看
- 🔄 会话历史
- 🎛️ 参数调整

## 💻 使用示例

### REST API

```bash
# 查找设备
curl http://localhost:8000/dm-camera/api/devices/find/

# 连接设备
curl -X POST http://localhost:8000/dm-camera/api/connect/

# 捕获深度图
curl -X POST http://localhost:8000/dm-camera/api/capture/ \
  -H "Content-Type: application/json" \
  -d '{"frame_type":"DEPTH","save_record":true}'
```

### Python代码

```python
from apps.dm_camera.services import DMCameraService

# 使用服务类
service = DMCameraService()
service.connect()
service.start_stream()
result = service.capture('DEPTH')
print(result['preview_url'])
```

### JavaScript前端

```javascript
// 捕获深度图
const response = await fetch('/dm-camera/api/capture/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ frame_type: 'DEPTH' })
});
const data = await response.json();
console.log(data.data.preview_url);
```

## 🧪 测试

### 测试脚本

```bash
# Python单元测试
python test_dm_camera.py              # 运行所有测试
python test_dm_camera.py --test find  # 仅测试查找设备

# REST API测试
python test_dm_camera_api.py          # API完整测试
```

### 集成检查

```bash
# 运行完整检查
python check_dm_camera_setup.py
```

## 📦 技术栈

- **Python**: 3.12 (64位)
- **Django**: 5.2+
- **SDK绑定**: ctypes
- **数据处理**: numpy, Pillow
- **存储**: SQLite
- **API**: REST (JSON)

## 🏗️ 架构设计

```
┌─────────────────────────────────────────┐
│           前端 / 客户端                  │
│  (Web UI / JavaScript / Python)         │
└─────────────┬───────────────────────────┘
              │ HTTP/REST API
┌─────────────▼───────────────────────────┐
│         REST API层 (views.py)           │
│        统一的JSON响应格式                │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│      业务逻辑层 (services.py)            │
│   单例服务、会话管理、数据处理           │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│     SDK包装层 (sdk_wrapper.py)          │
│     ctypes绑定、异常处理                 │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│      C SDK (dm_c_sdk.dll)               │
│          硬件驱动层                      │
└─────────────┬───────────────────────────┘
              │
         ┌────▼────┐
         │ DM相机  │
         └─────────┘
```

## 📊 API端点总览

### 设备控制 (7个)
- `GET  /api/devices/find/` - 查找设备
- `POST /api/connect/` - 连接设备
- `POST /api/disconnect/` - 断开设备
- `POST /api/stream/start/` - 开启数据流
- `POST /api/stream/stop/` - 停止数据流
- `POST /api/capture/` - 捕获一帧
- `GET  /api/status/` - 获取状态

### 配置管理 (5个)
- `GET    /api/configs/` - 列出配置
- `POST   /api/configs/create/` - 创建配置
- `GET    /api/configs/{id}/` - 获取配置
- `PUT    /api/configs/{id}/update/` - 更新配置
- `DELETE /api/configs/{id}/delete/` - 删除配置

### 采集记录 (2个)
- `GET /api/captures/` - 列出记录
- `GET /api/captures/{id}/` - 获取详情

## 🔍 目录结构

```
apps/dm_camera/           # DM相机Django应用
├── sdk_wrapper.py        # SDK包装器
├── services.py           # 服务层
├── views.py              # REST API
├── models.py             # 数据模型
├── urls.py               # URL配置
├── admin.py              # Admin配置
└── migrations/           # 数据库迁移

templates/
└── dm_camera_demo.html   # 演示页面

media/dm_camera/          # 数据存储
├── captures/             # 原始数据
└── previews/             # 预览图

文档/
├── DM_CAMERA_README.md                    # 完整文档
├── DM_CAMERA_QUICKSTART.md                # 快速入门
├── DM_CAMERA_INTEGRATION_SUMMARY.md       # 集成总结
└── DEPLOYMENT_GUIDE_DM_CAMERA.md          # 部署指南

测试/
├── test_dm_camera.py             # Python测试
├── test_dm_camera_api.py         # API测试
└── check_dm_camera_setup.py      # 集成检查
```

## ⚠️ 注意事项

### 硬件要求
- DM 3D深度相机（如 LWP-DM02C）
- 千兆以太网连接（推荐）
- Windows 10/11 64位系统

### 网络配置
- 相机和电脑需在同一网段
- 默认相机IP通常为 192.168.1.x
- 确保防火墙允许通信

### Python环境
- 必须使用64位Python（匹配x64 DLL）
- 推荐Python 3.10+
- 所有依赖已在requirements.txt中

## 🐛 故障排查

### 常见问题

1. **找不到设备** → 检查网络连接和IP配置
2. **DLL加载失败** → 确认Python是64位版本
3. **连接超时** → 检查防火墙和网络延迟
4. **捕获失败** → 确保数据流已开启

详细排查步骤请查看 [DEPLOYMENT_GUIDE_DM_CAMERA.md](DEPLOYMENT_GUIDE_DM_CAMERA.md)

## 📈 性能指标

- **帧率**: 最高30fps（取决于配置）
- **分辨率**: 640×480（可配置）
- **延迟**: <100ms（局域网）
- **并发**: 支持单设备单连接

## 🔄 更新日志

### v1.0.0 (当前版本)
- ✅ 初始版本发布
- ✅ 完整的SDK集成
- ✅ REST API实现
- ✅ Web演示页面
- ✅ 完善的文档

## 📞 技术支持

### 获取帮助

1. 查阅文档（推荐从快速入门开始）
2. 运行检查脚本诊断问题
3. 查看测试脚本示例代码
4. 检查SDK官方文档

### 联系方式

- 项目维护: [你的联系方式]
- SDK支持: 查看SDK文档

## 📄 许可证

本集成代码采用 [你的许可证]
DM相机SDK版权归厂商所有

---

## 🎉 开始使用

```bash
# 1. 检查集成
python check_dm_camera_setup.py

# 2. 运行测试（可选）
python test_dm_camera.py --test find

# 3. 启动服务
python manage.py runserver

# 4. 访问演示
# 浏览器打开: http://localhost:8000/dm-camera/
```

**祝你使用愉快！** 🚀

---

**版本**: 1.0.0  
**状态**: ✅ 生产就绪  
**更新**: 2024
