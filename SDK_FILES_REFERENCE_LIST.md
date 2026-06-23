# 相机SDK文件引用清单

## 📋 概览

Django项目中使用的所有相机SDK文件清单。这些文件都**保持在原位置**，通过动态引用方式使用，**没有复制**到Django项目中。

---

## 🔴 被直接引用的SDK文件

### 1. Python API模块（2个文件）

#### 📄 LW_DM_Api.py
```
位置: d:\workspace2\DM-Host-Computer-SDK\DM上位机&SDK\SDK\1.2.3\Python\API\zh\LW_DM_Api.py
大小: ~1659行
作用: SDK主要接口类和方法
引用位置: apps/dm_camera/sdk_wrapper.py 第22行
导入内容:
  - LWDM3DCamera      (SDK主类)
  - DeviceInfo        (设备信息结构)
  - ParsingData       (帧数据解析类)
  - FilterParam       (滤波参数结构)
```

#### 📄 LW_DM_Type.py
```
位置: d:\workspace2\DM-Host-Computer-SDK\DM上位机&SDK\SDK\1.2.3\Python\API\zh\LW_DM_Type.py
大小: ~300行
作用: SDK数据类型和枚举定义
引用位置: apps/dm_camera/sdk_wrapper.py 第23-26行
导入内容:
  - LWReturnCode      (返回码枚举)
  - LWSensorType      (传感器类型枚举)
  - LWTriggerMode     (触发模式枚举)
  - LWExposureMode    (曝光模式枚举)
  - LWFrameType       (帧类型枚举)
  - LWDataRecvType    (数据接收类型枚举)
  还有20+个其他类型定义
```

### 2. 动态库文件（1个DLL）

#### 🔧 dm_c_sdk.dll
```
位置: d:\workspace2\DM-Host-Computer-SDK\DM上位机&SDK\SDK\1.2.3\C\lib\windows\x64\dm_c_sdk.dll
架构: x64 (64位)
作用: C语言SDK核心库，所有底层功能实现
加载方式: ctypes.cdll.LoadLibrary()
引用位置: apps/dm_camera/sdk_wrapper.py 第50行
```

---

## 🟡 间接使用的SDK文件

### 3. C语言头文件（2个）

这些是SDK的原始C头文件，Python代码间接依赖它们（Python API是对这些C API的包装）

#### 📄 LWDMApi.h
```
位置: d:\workspace2\DM-Host-Computer-SDK\DM上位机&SDK\SDK\1.2.3\C\include\en\LWDMApi.h
大小: ~724行
作用: C SDK的API函数声明
说明: LW_DM_Api.py 是对这个文件中的函数的Python包装
```

#### 📄 LWDMType.h
```
位置: d:\workspace2\DM-Host-Computer-SDK\DM上位机&SDK\SDK\1.2.3\C\include\en\LWDMType.h
大小: ~300行
作用: C SDK的数据类型定义
说明: LW_DM_Type.py 是对这个文件中的类型的Python包装
```

### 4. 导入库文件（1个）

#### 📄 dm_c_sdk.lib
```
位置: d:\workspace2\DM-Host-Computer-SDK\DM上位机&SDK\SDK\1.2.3\C\lib\windows\x64\dm_c_sdk.lib
作用: C/C++编译时使用的导入库
说明: 我们的Python项目不直接使用它（C项目才用）
```

---

## 📊 完整的SDK文件结构

```
d:\workspace2\DM-Host-Computer-SDK\
└── DM上位机&SDK\
    └── SDK\
        └── 1.2.3\
            ├── README.md
            ├── LICENSE
            ├── C\                           ← C SDK
            │   ├── doc\
            │   │   ├── en\html\            (C API文档)
            │   │   └── zh\html\            (C API文档)
            │   ├── include\
            │   │   ├── en\
            │   │   │   ├── LWDMApi.h       ✅ 间接使用
            │   │   │   └── LWDMType.h      ✅ 间接使用
            │   │   └── zh\
            │   │       ├── LWDMApi.h       (中文版)
            │   │       └── LWDMType.h      (中文版)
            │   ├── lib\
            │   │   ├── linux\              (Linux库)
            │   │   └── windows\
            │   │       ├── x86\            (32位库)
            │   │       └── x64\
            │   │           ├── dm_c_sdk.dll    ✅ 直接使用
            │   │           └── dm_c_sdk.lib    (不使用)
            │   └── samples\                (C示例代码)
            │
            ├── Python\                      ← Python SDK
            │   ├── API\
            │   │   ├── en\                 (英文版)
            │   │   └── zh\
            │   │       ├── LW_DM_Api.py    ✅ 直接导入
            │   │       └── LW_DM_Type.py   ✅ 直接导入
            │   └── samples\                (Python示例)
            │
            ├── python_sdk\                 (空目录)
            └── C#\                         (C# SDK，不使用)
```

---

## 🎯 使用位置追踪

### 1️⃣ 在 sdk_wrapper.py 中的使用

```python
# 第15行：指向DLL文件
DLL_PATH = SDK_PATH / "C/lib/windows/x64/dm_c_sdk.dll"

# 第19行：添加Python API搜索路径
sys.path.insert(0, str(PYTHON_API_PATH))
# PYTHON_API_PATH = "...SDK/1.2.3/Python/API/zh"

# 第22-26行：导入SDK模块
from LW_DM_Api import LWDM3DCamera, DeviceInfo, ParsingData, FilterParam
from LW_DM_Type import (
    LWReturnCode, LWSensorType, LWTriggerMode,
    LWExposureMode, LWFrameType, LWDataRecvType
)

# 第50行：加载DLL
self.camera = LWDM3DCamera(str(DLL_PATH))
```

### 2️⃣ 在 services.py 中的使用

```python
# 第19行：导入类型
from LW_DM_Type import LWTriggerMode, LWFrameType, LWDataRecvType

# 在各个方法中使用这些类型来控制相机
trigger_mode_map = {
    'ACTIVE': LWTriggerMode.LW_TRIGGER_ACTIVE,
    'SOFT': LWTriggerMode.LW_TRIGGER_SOFT,
    'HARD': LWTriggerMode.LW_TRIGGER_HARD,
}
```

### 3️⃣ 在 views.py 中的使用

```python
# views.py 不直接导入SDK文件
# 而是通过 services.py 使用服务层
from .services import DMCameraService
```

---

## 📈 文件依赖关系

```
Django View (views.py)
    ↓ 调用
Service Layer (services.py)
    ↓ 使用类型
LW_DM_Type.py ✅ (引用)
    ↓
SDK_Wrapper (sdk_wrapper.py)
    ├─ 导入 LW_DM_Api.py ✅
    ├─ 导入 LW_DM_Type.py ✅
    └─ 加载 dm_c_sdk.dll ✅
           ↓
    (dm_c_sdk.dll 依赖)
    ├─ LWDMApi.h (源定义)
    ├─ LWDMType.h (源定义)
    └─ (其他系统库)
```

---

## 🔍 SDK文件详细信息

### Python API (LW_DM_Api.py) 中的主要类和方法

```python
class LWDM3DCamera:
    # 主要方法
    def LWInitializeResources()           # 初始化
    def LWCleanupResources()              # 清理
    def LWGetDeviceInfoList()             # 获取设备列表
    def LWOpenDevice(handle)              # 打开设备
    def LWCloseDevice(handle)             # 关闭设备
    def LWStartStream(handle)             # 开启数据流
    def LWStopStream(handle)              # 停止数据流
    def LWSetFrameRate(handle, fps)       # 设置帧率
    def LWSetExposureTime(...)            # 设置曝光时间
    def LWSetTriggerMode(handle, mode)    # 设置触发模式
    def LWGetFrame(handle, type)          # 获取帧数据
    # ... 还有 100+ 个其他方法
```

### Python API (LW_DM_Type.py) 中的主要类型

```python
class LWReturnCode(Enum):
    LW_RETURN_OK = 0x00                   # 成功
    LW_RETURN_TIMEOUT = 0x20              # 超时
    # ... 30+ 个其他返回码

class LWFrameType(Enum):
    LW_DEPTH_FRAME = 0B000000001          # 深度图
    LW_IR_FRAME = 0B000000100             # IR图
    LW_POINTCLOUD_FRAME = 0B000001000     # 点云
    # ... 其他帧类型

class LWTriggerMode(Enum):
    LW_TRIGGER_ACTIVE = 0x00              # 连续模式
    LW_TRIGGER_SOFT = 0x01                # 软触发
    LW_TRIGGER_HARD = 0x02                # 硬触发
    # ... 其他触发模式

# 还有 20+ 个其他 Enum 类
# 以及 10+ 个 Structure 类 (ctypes.Structure)
```

---

## ✅ 被使用的SDK功能清单

我的集成中实际使用的SDK功能：

```
✅ 设备发现和管理
   - LWGetDeviceInfoList()
   - LWOpenDevice()
   - LWCloseDevice()

✅ 数据流控制
   - LWStartStream()
   - LWStopStream()
   - LWGetFrameReady()
   - LWGetFrame()

✅ 相机配置
   - LWSetFrameRate()
   - LWSetExposureTime()
   - LWSetTriggerMode()
   - LWSetResolution()

✅ 滤波器控制
   - LWSetConfidenceFilterParams()
   - LWSetFlyingPixelsFilterParams()
   - LWSetSpatialFilterParams()
   - LWSetTimeFilterParams()

✅ 信息查询
   - LWGetDeviceSN()
   - LWGetDeviceVersion()
   - LWGetIntrinsicParam()
   - LWGetNetworkInfo()

✅ 其他功能
   - LWGetLibVersion()
   - LWGetReturnCodeDescriptor()
```

---

## 🚫 未使用的SDK功能

以下功能在我的集成中**没有使用**：

```
❌ RGB相关
   - LWHasRgbModule()
   - LWGetRgbSensorGain()
   - LWSetRgbSensorGamma()
   等 (RGB相机特定功能)

❌ IMU相关
   - LWGetIMUData()
   - LWSetIMUFrequency()
   等 (惯性测量相关)

❌ 点云处理
   - LWIMURotatePointCloud()
   - LWSavePointCloudAsPCDFile()
   等 (点云文件操作)

❌ 硬件标定
   - LWSetNetworkInfo()
   - LWRebootDevice()
   等 (网络配置和硬件设置)

❌ Linux相关
   (Windows 64位库已足够)
```

---

## 📌 总结

### 直接使用的SDK文件：3个
1. ✅ `LW_DM_Api.py` - Python主接口
2. ✅ `LW_DM_Type.py` - Python类型定义
3. ✅ `dm_c_sdk.dll` - 核心动态库

### 间接依赖的SDK文件：3个
1. 🟡 `LWDMApi.h` - C源头
2. 🟡 `LWDMType.h` - C源头
3. 🟡 `dm_c_sdk.lib` - C导入库

### SDK文件总数：
- C SDK: 2个头文件 + 2个库文件 = 4个
- Python SDK: 2个Python模块 = 2个
- **总计: 6个被实际使用**

### 所有文件位置：
```
Base: d:\workspace2\DM-Host-Computer-SDK\DM上位机&SDK\SDK\1.2.3\
```

**没有任何SDK文件被复制到Django项目中，全部动态引用！** ✅
