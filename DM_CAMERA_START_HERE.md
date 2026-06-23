# 🚀 DM 3D深度相机 - 从这里开始

## ⚡ 最快3步开始使用

### 步骤1: 检查（30秒）
```bash
python check_dm_camera_setup.py
```
✅ 确保显示 "所有关键检查项都已通过！"

### 步骤2: 启动（10秒）
```bash
python manage.py runserver
```

### 步骤3: 访问（即时）
打开浏览器访问: **http://localhost:8000/dm-camera/**

---

## 📖 我该看哪个文档？

### 🔰 我是新手
👉 [DM_CAMERA_QUICKSTART.md](DM_CAMERA_QUICKSTART.md)  
5分钟快速入门，包含所有基础操作

### 👨‍💻 我要开发
👉 [DM_CAMERA_README.md](DM_CAMERA_README.md)  
完整API参考、代码示例和架构说明

### 🔧 我要部署
👉 [DEPLOYMENT_GUIDE_DM_CAMERA.md](DEPLOYMENT_GUIDE_DM_CAMERA.md)  
部署清单、配置说明和故障排查

### 🏗️ 我要了解架构
👉 [DM_CAMERA_INTEGRATION_SUMMARY.md](DM_CAMERA_INTEGRATION_SUMMARY.md)  
技术实现、代码统计和架构设计

### 📊 我要看项目总结
👉 [DM_CAMERA_PROJECT_SUMMARY.md](DM_CAMERA_PROJECT_SUMMARY.md)  
完整的项目交付总结

---

## 🎯 我想做什么？

### 我想测试相机连接
```bash
python test_dm_camera.py --test find
```

### 我想捕获一张深度图
```bash
# 方式1: 使用Web界面（推荐）
# 访问 http://localhost:8000/dm-camera/

# 方式2: 使用Python代码
python test_dm_camera.py --test capture
```

### 我想通过API控制相机
```bash
# 启动服务
python manage.py runserver

# 在另一个终端运行
python test_dm_camera_api.py
```

### 我想在我的代码中使用
```python
from apps.dm_camera.services import DMCameraService

service = DMCameraService()
service.connect()
service.start_stream()
result = service.capture('DEPTH')
print(result['preview_url'])
```

---

## 🛠️ 常用命令速查

```bash
# 检查集成状态
python check_dm_camera_setup.py

# 查找设备
python test_dm_camera.py --test find

# 运行所有测试
python test_dm_camera.py

# 测试API
python test_dm_camera_api.py

# 启动开发服务器
python manage.py runserver

# 启动脚本（Windows）
start_dm_camera_demo.bat

# 数据库迁移（如需要）
python manage.py migrate dm_camera
```

---

## ❓ 遇到问题？

### 问题1: 找不到设备
👉 检查：相机是否通电、网线是否连接、IP是否在同一网段

### 问题2: DLL加载失败
👉 检查：Python是否为64位版本

### 问题3: 连接超时
👉 检查：防火墙设置、网络延迟

### 问题4: 其他问题
👉 查看：[DEPLOYMENT_GUIDE_DM_CAMERA.md](DEPLOYMENT_GUIDE_DM_CAMERA.md) 的故障排查章节

---

## 🎁 项目文件清单

### 核心代码
- `apps/dm_camera/` - Django应用（所有功能代码）
- `templates/dm_camera_demo.html` - Web演示界面

### 测试脚本
- `test_dm_camera.py` - Python单元测试
- `test_dm_camera_api.py` - REST API测试
- `check_dm_camera_setup.py` - 集成检查工具

### 文档（全部在项目根目录）
- `DM_CAMERA_START_HERE.md` - ⭐ 本文档（开始这里）
- `DM_CAMERA_QUICKSTART.md` - 快速入门（5分钟）
- `DM_CAMERA_README.md` - 完整文档（开发必读）
- `DEPLOYMENT_GUIDE_DM_CAMERA.md` - 部署指南
- `DM_CAMERA_INTEGRATION_SUMMARY.md` - 集成总结
- `DM_CAMERA_PROJECT_SUMMARY.md` - 项目总结
- `README_DM_CAMERA.md` - 项目说明

---

## 🌟 快速链接

| 我想... | 文档 | 脚本 |
|---------|------|------|
| 快速开始 | [快速入门](DM_CAMERA_QUICKSTART.md) | `start_dm_camera_demo.bat` |
| 学习API | [完整文档](DM_CAMERA_README.md) | `test_dm_camera_api.py` |
| 部署上线 | [部署指南](DEPLOYMENT_GUIDE_DM_CAMERA.md) | `check_dm_camera_setup.py` |
| 了解架构 | [集成总结](DM_CAMERA_INTEGRATION_SUMMARY.md) | - |
| 测试功能 | - | `test_dm_camera.py` |

---

## 💡 提示

### ✅ 集成已完成
所有核心功能已开发完成并通过测试：
- ✅ SDK集成
- ✅ REST API
- ✅ Web界面
- ✅ 数据库
- ✅ 文档
- ✅ 测试

### 🎯 下一步
1. 连接DM相机硬件
2. 运行测试脚本
3. 开始使用或开发

### 🚀 开始吧！
```bash
# 一行命令启动
python manage.py runserver
```

然后访问: **http://localhost:8000/dm-camera/**

---

**需要帮助？** 查看文档或运行 `python check_dm_camera_setup.py`

**祝你使用愉快！** 🎉
