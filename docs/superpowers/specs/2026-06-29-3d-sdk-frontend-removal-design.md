# 3D 相机 SDK 前端清理与配置文件接入设计

## 目标

只删除料架定位工作台中面向开发调试的 3D 相机 SDK 可视化内容，同时保留独立的 `/dm-camera/` 开发页面、模板、视图以及全部 `/dm-camera/api/*`。相机运行参数改为由后端从项目目录 `3d_SDK/tofconfig` 读取，不再依赖料架定位页编辑并保存 SDK 参数。

## 范围

### 删除

- 料架定位工作台中的“SDK 调试”按钮。
- 料架定位工作台中的 SDK 调试侧栏、遮罩、专用样式和交互脚本。
- 只服务于上述料架定位页 SDK drawer 的前端配置、DOM 标记和 URL 配置。

### 保留

- 独立的 `/dm-camera/` 开发页面根路由 `path('', views.demo_page, name='demo')`。
- `apps/dm_camera/views.py` 中的 `demo_page`。
- `templates/dm_camera_demo.html`。
- 全部 `/dm-camera/api/*` 后端 API。
- `apps.dm_camera` 相机服务、SDK 封装、模型和正式采集逻辑。
- 料架定位、点云采集、自动定位和 PLC 写入功能。
- 数据库中的 `DMCameraConfig`，用于设备选择、会话记录和现有数据兼容；相机成像参数以 `tofconfig` 为准。

## 配置文件读取

`3d_SDK/tofconfig` 是逐字节与 `0xFF` 异或后的 UTF-8 JSON。后端读取器负责：

1. 从 `BASE_DIR / "3d_SDK" / "tofconfig"` 读取二进制内容。
2. 对每个字节执行异或解码。
3. 使用 UTF-8 解码并解析 JSON。
4. 校验正式采集所需字段及值类型。
5. 将厂家字段映射到现有 SDK 调用：
   - `fps_value` → 帧率。
   - `exposure_time[0]` → ToF 曝光时间。
   - `trigger_mode` → SDK 触发模式枚举。
   - `is_confidence_filtering`、`confidence_filter_value` → 置信度滤波。
   - `is_fly_filtering`、`fly_filter_value` → 飞点滤波。
   - `is_spatial_filtering`、`spatial_filter_value` → 空间滤波。

厂家文件中的其他参数暂不伪造 SDK 映射；只有当前 SDK 封装明确支持的参数才传入相机。

## 数据流

正式采集请求进入现有料架定位服务后，相机服务建立连接，读取并校验 `tofconfig`，再把映射后的配置传给 SDK。数据库配置仍可提供设备序列号等兼容信息，但不覆盖文件中的成像和滤波参数。

如果配置文件缺失、解码失败、JSON 无效或必需字段不合法，连接或采集请求返回明确错误并停止，不静默回退到开发默认参数。

## 前端清理

料架定位工作台保留业务操作：选择配方、采集点云、绘制 ROI、计算偏差、保存结果和自动触发。删除该页面所有 `sdk-*` DOM、专用样式、事件监听和 SDK 调试 URL 配置，确保工作台不再暴露设备发现、连接恢复、参数编辑、测试采集或厂家调试入口。

该清理不涉及独立相机开发页面。`/dm-camera/` 继续渲染 `templates/dm_camera_demo.html`，其 `demo_page` 视图和全部 `/dm-camera/api/*` 路由均保留。

## 测试与验收

- 单元测试验证 `tofconfig` 的异或解码、JSON 解析和字段映射。
- 单元测试验证文件缺失、损坏和字段非法时返回清晰错误。
- 相机服务测试验证连接时采用文件参数，而非前端或数据库中的成像参数。
- 页面测试验证料架定位页不再包含 SDK 调试按钮、侧栏和调试 URL。
- `/dm-camera/` 请求返回 HTTP 200，或至少 URL 解析仍指向 `views.demo_page`。
- `templates/dm_camera_demo.html` 继续存在，且 `/dm-camera/api/*` 路由继续保留。
- 运行 Django system check 和相关测试集，确认正式料架定位链路不受影响。

## 非目标

- 不删除或重构独立 `/dm-camera/` 开发页面。
- 不删除相机 SDK DLL、Python 封装或后端采集 API。
- 不重构料架定位算法。
- 不为 `tofconfig` 新建可视化编辑器。
- 不改变厂家配置文件的编码格式或内容。
