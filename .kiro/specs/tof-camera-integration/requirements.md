# Requirements Document

## Introduction

本文档描述将 LWP-DM02C ToF 3D 深度相机 SDK 集成到 AutomaticOrder Django 工业自动化系统的需求。
集成以独立 Django App（`apps/tof_camera`）方式实现，提供 REST API 和 WebSocket 接口，支持相机控制、
数据采集和实时流推送，不修改现有系统其他模块。

**项目技术栈确认：**
- Django 6.0.6
- 数据库：SQLite（沿用现有项目配置）
- 新增依赖：djangorestframework、channels、django-q2
- 相机 SDK：厂商 Python 封装（`LW_DM_Api.py` + `LW_DM_Type.py`）

## Glossary

- **ToF_Camera**: Time-of-Flight 3D 深度相机，型号 LWP-DM02C
- **Camera_SDK**: 厂商 Python API（基于 ctypes 调用 C DLL `dm_c_sdk.dll`）
- **tof_camera_app**: 新增的 Django App，路径 `apps/tof_camera`
- **Camera_Manager**: 单例管理器，负责多相机生命周期（连接、流、回调）
- **Frame_Data**: 相机采集的帧（深度/IR/RGB/点云）
- **Device_Handle**: 相机设备的唯一 uint64 句柄
- **Capture_Session**: 单次采集的记录（配置快照 + 结果文件路径）
- **Stream_Session**: WebSocket 实时流会话

## Requirements

### Requirement 1: 相机设备管理

**User Story:** 作为操作员，我希望通过 Web 界面发现和管理连接的 ToF 相机，以便在生产中使用。

#### Acceptance Criteria

1. WHEN 系统调用设备扫描接口，THE Camera_Manager SHALL 调用 `LWGetDeviceInfoList` 并返回所有可用设备的 SN、IP、类型、handle 信息
2. WHEN REST API 接收到打开设备请求并提供有效 Device_Handle，THE Camera_Manager SHALL 调用 `LWOpenDevice` 并将状态更新为 `connected`
3. WHEN REST API 接收到关闭设备请求，THE Camera_Manager SHALL 先调用 `LWStopStream`（如流已开启）再调用 `LWCloseDevice`
4. WHEN 网络异常断开，THE Camera_Manager SHALL 通过已注册的 `LWRegisterNetworkMonitoringCallback1` 感知异常，更新数据库状态为 `disconnected` 并写入日志
5. THE SQLite 数据库 SHALL 存储相机注册信息（SN、IP、别名、状态、上次连接时间）
6. WHEN 同一 handle 已处于打开状态再次请求打开，THE Camera_Manager SHALL 返回错误信息而不重复调用 SDK

### Requirement 2: 相机参数配置

**User Story:** 作为操作员，我希望通过 API 设置相机曝光、帧率、分辨率和滤波器，以适应不同拍摄场景。

#### Acceptance Criteria

1. WHEN REST API 接收到配置请求且参数合法，THE Camera_Manager SHALL 批量调用对应 SDK 方法（曝光/帧率/分辨率/HDR/触发模式/滤波器）
2. WHEN 设置分辨率后，THE Camera_Manager SHALL 提示客户端需要重新打开设备（SDK 要求）
3. WHEN 参数超出允许范围（TOF 分辨率: 640×480/320×240/160×120；RGB: 1600×1200/800×600/640×480），THE tof_camera_app SHALL 在进入 SDK 前返回 400 错误
4. WHEN REST API 接收到保存配置请求，THE Camera_Manager SHALL 调用 `LWSaveConfigureInfo` 将配置持久化到设备
5. THE SQLite 数据库 SHALL 存储配置预设（名称、参数 JSON、关联相机 SN、创建时间）
6. WHEN REST API 接收到应用预设请求，THE tof_camera_app SHALL 从数据库读取配置并批量应用到指定相机

### Requirement 3: 单次数据采集

**User Story:** 作为操作员，我希望触发单次拍摄并获取深度/IR/RGB/点云数据，用于质量检测。

#### Acceptance Criteria

1. WHEN REST API 接收到采集请求，THE Camera_Manager SHALL 按顺序执行：设置参数 → `LWStartStream` → `LWGetFrameReady` → `LWGetFrame` → `LWStopStream`
2. WHEN 采集成功，THE tof_camera_app SHALL 将 Frame_Data 转为 NumPy 数组并以 Base64 JPEG（RGB/深度着色图）格式返回
3. WHEN 采集请求包含 `save=true`，THE tof_camera_app SHALL 将点云保存为 PCD 文件并在响应中返回文件下载路径
4. WHEN `LWGetFrameReady` 超时（默认 5 秒），THE Camera_Manager SHALL 调用 `LWStopStream` 清理并返回 504 错误
5. WHEN 采集完成，THE SQLite 数据库 SHALL 创建 Capture_Session 记录（相机 SN、时间、帧类型、文件路径、温度、IMU）
6. WHEN 采集的帧包含托盘识别数据，THE tof_camera_app SHALL 在响应中附加托盘姿态信息（位置、旋转角、置信度）

### Requirement 4: 实时视频流（WebSocket）

**User Story:** 作为操作员，我希望实时查看深度图和 RGB 图像流，以监控采集效果。

#### Acceptance Criteria

1. WHEN WebSocket 客户端连接到 `/ws/tof_camera/{sn}/stream/`，THE Stream_Session SHALL 建立并验证相机 SN 是否已注册
2. WHEN 流会话建立，THE Camera_Manager SHALL 调用 `LWStartStream` 并注册 `LWRegisterFrameReadyCallback1`
3. WHEN 帧就绪回调触发，THE Camera_Manager SHALL 获取帧数据并编码为 JPEG，通过 WebSocket 推送（含帧索引、时间戳、帧类型）
4. THE WebSocket_Server SHALL 限制推送帧率（可配置，默认 10 fps），超出则丢弃中间帧
5. WHEN 多客户端连接同一相机，THE Camera_Manager SHALL 复用同一数据流，向所有客户端广播
6. WHEN WebSocket 连接断开且无其他客户端，THE Camera_Manager SHALL 注销回调并调用 `LWStopStream`
7. WHEN 客户端发送 `{"action": "set_frame_type", "type": "depth"}` 消息，THE Stream_Session SHALL 切换推送的帧类型（depth/ir/rgb）

### Requirement 5: 异步任务（Django-Q2）

**User Story:** 作为系统用户，我希望批量采集等耗时操作在后台执行，API 立即返回任务 ID。

#### Acceptance Criteria

1. WHEN REST API 接收到批量采集请求（帧数 > 1），THE tof_camera_app SHALL 创建 Django-Q2 任务并立即返回任务 ID
2. WHEN 任务执行中，THE tof_camera_app SHALL 通过数据库记录更新进度（已采集帧数/总帧数）
3. WHEN 任务完成，THE SQLite 数据库 SHALL 更新任务状态为 `completed` 并记录结果文件路径列表
4. WHEN REST API 查询任务状态，THE tof_camera_app SHALL 返回状态、进度、错误信息（如有）

### Requirement 6: 错误处理与健康监控

**User Story:** 作为运维人员，我希望系统能优雅地处理相机错误并提供健康检查接口。

#### Acceptance Criteria

1. WHEN SDK 返回非零错误码，THE Camera_Manager SHALL 调用 `LWGetReturnCodeDescriptor` 获取描述并写入 Django logger
2. WHEN 设备温度（芯片）超过 85°C，THE tof_camera_app SHALL 写入警告日志并在 API 响应中附加温度告警标志
3. WHEN 连续 3 次操作失败，THE Camera_Manager SHALL 自动调用 `LWReconnectDevice`（超时 5000ms）尝试重连
4. WHEN REST API 请求 `GET /api/tof_camera/health/`，THE tof_camera_app SHALL 返回：Django 服务状态、数据库连通性、各相机连接状态
5. THE tof_camera_app SHALL 使用 Django 内置日志系统，INFO 级记录操作，ERROR 级记录异常

### Requirement 7: Django App 集成规范

**User Story:** 作为 Django 开发者，我希望 ToF 相机模块遵循现有项目规范，无缝集成。

#### Acceptance Criteria

1. THE tof_camera_app SHALL 放置在 `apps/tof_camera/`，命名遵循项目 `apps.*` 约定
2. THE tof_camera_app SHALL 使用 Django ORM 定义模型，并提供 migrations
3. THE tof_camera_app SHALL 在项目 `urls.py` 中以 `path('tof_camera/', include('apps.tof_camera.urls'))` 方式挂载
4. THE tof_camera_app SHALL 在 `settings.py` 的 `INSTALLED_APPS` 中注册，并在 `AUTOMATIC_ORDER` 配置块中添加 `TOF_CAMERA` 子配置
5. THE tof_camera_app SHALL 通过 `apps.py` 的 `ready()` 方法初始化 Camera_Manager 单例
6. THE tof_camera_app SHALL 不修改其他任何现有 app 的代码文件
7. THE tof_camera_app SHALL 在 `admin.py` 中注册所有模型到 Django Admin
