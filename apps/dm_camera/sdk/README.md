# DM相机SDK文件

## 📁 目录结构

```
apps/dm_camera/sdk/
├── __init__.py           # Python包初始化
├── LW_DM_Api.py          # SDK主接口（从原SDK复制）
├── LW_DM_Type.py         # SDK类型定义（从原SDK复制）
├── lib/
│   └── dm_c_sdk.dll      # SDK核心动态库（从原SDK复制）
└── README.md             # 本文档
```

## 📋 文件来源

所有文件都是从DM相机原始SDK复制而来：

### 1. Python API文件
```
来源: d:\workspace2\DM-Host-Computer-SDK\DM上位机&SDK\SDK\1.2.3\Python\API\zh\
文件:
  - LW_DM_Api.py    (SDK主接口，~1659行)
  - LW_DM_Type.py   (类型定义，~300行)
```

### 2. 动态库文件
```
来源: d:\workspace2\DM-Host-Computer-SDK\DM上位机&SDK\SDK\1.2.3\C\lib\windows\x64\
文件:
  - dm_c_sdk.dll    (64位Windows DLL)
```

## ⚠️ 重要说明

### 版本信息
- SDK版本: 1.2.3
- 复制日期: 2024
- 架构: Windows x64

### 更新SDK
如果需要更新SDK版本：

1. 从新SDK复制相应文件覆盖本目录
2. 确保文件名保持一致
3. 运行测试验证兼容性

```bash
# 复制新的Python API
copy "新SDK路径\Python\API\zh\LW_DM_*.py" apps\dm_camera\sdk\

# 复制新的DLL
copy "新SDK路径\C\lib\windows\x64\dm_c_sdk.dll" apps\dm_camera\sdk\lib\

# 运行测试
python test_dm_camera.py
```

### 文件说明

#### LW_DM_Api.py
- 功能: SDK的Python接口封装
- 主类: LWDM3DCamera
- 方法: 100+ 个设备控制和数据采集方法
- 依赖: LW_DM_Type.py, dm_c_sdk.dll

#### LW_DM_Type.py
- 功能: SDK的数据类型和枚举定义
- 包含: 30+ 个枚举类型，10+ 个结构体
- 类型: 返回码、帧类型、触发模式等

#### dm_c_sdk.dll
- 功能: SDK核心库
- 架构: x64 (64位)
- 依赖: Visual C++ Runtime
- 大小: ~数MB

## 🔧 使用方式

SDK文件通过sdk_wrapper.py自动加载：

```python
# sdk_wrapper.py 中的加载代码
SDK_DIR = Path(__file__).parent / "sdk"
DLL_PATH = SDK_DIR / "lib" / "dm_c_sdk.dll"

sys.path.insert(0, str(SDK_DIR))
from LW_DM_Api import LWDM3DCamera
```

## 📝 许可证

这些文件归DM相机SDK原厂商所有，请遵守原SDK的许可协议。

## 🔗 相关文档

- 原始SDK文档: SDK安装目录下的doc文件夹
- 集成文档: ../../DM_CAMERA_README.md
- API参考: 查看LW_DM_Api.py中的文档字符串
