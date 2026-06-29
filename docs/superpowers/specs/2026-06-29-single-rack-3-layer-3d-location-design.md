# 单料架三层 3D 深度相机料架定位模块设计

日期：2026-06-29
范围：在现有 AutomaticOrder `apps/vision` 3D 料架定位能力上做兼容增强，补齐“单料架三层”闭环。不新建 app，不推翻已有 2D 泡棉检测、生产、流程、设备、MES 页面。

## 1. 背景

项目中已经存在 3D 料架定位雏形：

- `RackLocationRecipe`：3D 料架定位配方主表。
- `RackLocationROI3D`：料架坐标系下的三维 ROI。
- `RackLocationResult`：定位结果记录。
- `Rack3DLocator` / `RackLocationService`：采集、自动对齐、定位、PLC 写入入口。
- `/vision/api/vision/3d/...`：3D API 雏形。
- `rack_locator_panel.html` / `rack_locator_workbench.js`：3D 工作台页面。

本次不另起一套 `Rack3DRecipe` 和 `Rack3DLocationResult`，而是在上述模块中收敛语义、补齐单料架三层流程，并保留旧字段和旧接口兼容。

## 2. 目标

- 支持单料架完整周期 4 次 3D 拍照：
  - `layer_index=0`：整体料架定位。
  - `layer_index=1`：第 1 层局部定位。
  - `layer_index=2`：第 2 层局部定位。
  - `layer_index=3`：第 3 层局部定位。
- 对外统一暴露 `locate_type=GLOBAL/LAYER` 和 `layer_index=0/1/2/3`。
- 复用现有 `RackLocationRecipe`、`RackLocationROI3D`、`RackLocationResult`。
- ROI 必须保存为三维空间盒：`x_min/x_max/y_min/y_max/z_min/z_max`。
- 原始点云只用于观察；必须自动对齐成功后，才能在矫正视图上保存生产 ROI。
- 打通手动闭环：相机测试、采集、自动对齐、保存 ROI、计算偏差、写入 PLC。
- 定位 NG 时禁止写入有效补偿，并记录错误码和错误描述。
- 不影响现有 2D 泡棉检测、production、workflow、devices、MES、traceability 页面。

## 3. 非目标

- 不实现左右双料架生产流程，本阶段只按单料架处理。
- 不强制引入 Open3D 或大型点云依赖。
- 不重构真实相机 SDK 或真实 PLC 协议。
- 不删除旧的 `layer_no`、`mode=global/local`、旧 `/api/rack-location/...` 兼容入口。
- 不把硬件通信逻辑写进算法类。

## 4. 兼容语义

内部继续保留现有字段，外部新增统一语义映射：

| 新语义 | 旧/内部语义 | 说明 |
| --- | --- | --- |
| `locate_type=GLOBAL` | `RackLocationROI3D.mode=global` | 整体定位 |
| `locate_type=LAYER` | `RackLocationROI3D.mode=local` | 分层局部定位 |
| `layer_index=0` | `layer_no=0` 或全局 ROI `layer_no=None` | 整体定位入口 |
| `layer_index=1/2/3` | `layer_no=1/2/3` | 三层局部定位 |

API 响应同时返回 `locate_type`、`layer_index` 和兼容字段 `layer_no`，便于旧页面和测试继续工作。

## 5. 数据模型

### 5.1 RackLocationRecipe

继续作为 3D 定位配方主表。必要时新增兼容字段：

- `locate_type`：可选，记录配方默认用途，值为 `GLOBAL` / `LAYER`。
- `photo_pose_name`：兼容需求中的拍照位名称；可映射或同步现有 `capture_pose_name`。
- `robot_pose_code`：机器人/PLC 流程拍照位编码。
- `total_layers`：兼容需求命名；可映射或同步现有 `layer_count`。

如果迁移风险较高，第一阶段优先用属性、序列化字段和 `result_data` 暴露这些语义，避免破坏旧数据。

### 5.2 RackLocationROI3D

继续保存三维 ROI：

- `recipe`
- `roi_name`
- `mode=global/local`
- `layer_no`
- `coordinate_system=rack`
- `x_min/x_max/y_min/y_max/z_min/z_max`
- `enabled`

规则：

- `GLOBAL` ROI 保存为 `mode=global`，`layer_no=None`。
- `LAYER` ROI 保存为 `mode=local`，`layer_no=1/2/3`。
- 保存 ROI 时必须经过自动对齐状态校验。
- `x_min < x_max`、`y_min < y_max`、`z_min < z_max`。

### 5.3 RackLocationResult

继续作为结果表。为满足整体 + 分层补偿追溯，优先使用新增字段；若迁移冲突，则放入 `result_data` 并同步核心旧字段：

- `rack_barcode`
- `locate_type`
- `layer_index`
- `offset_x/offset_y/offset_z/offset_rz`
- `layer_offset_x/layer_offset_y/layer_offset_z/layer_offset_rz`
- `final_offset_x/final_offset_y/final_offset_z/final_offset_rz`
- `confidence`
- `is_success`
- `error_code`
- `error_message`
- `raw_data_path`
- `result_image_path`
- `aligned_image_path`
- `plc_write_status`

旧字段 `layer_no`、`side`、`actual_x/y/z` 保留。整体定位时 `offset_*` 表示整体粗定位偏差；层定位时 `offset_*` 可继续保存当前层输出，`result_data` 明确记录 overall/layer/final 三类补偿。

## 6. 服务层

### 6.1 深度相机适配

复用现有 `apps.dm_camera` 和 `DMCameraRackFrameProvider`，在 `apps/vision/rack_location.py` 中保持清晰边界：

- `DepthCameraAdapter`：抽象接口语义，可由现有 provider 承担。
- `MockDepthCameraAdapter`：使用 `build_sample_pointcloud()` 和本地 mock 数据。
- `RealDepthCameraAdapter`：预留真实 SDK 接入，当前委托 DM 相机服务。

相机模块只负责采集、保存原始深度图、原始点云和生成预览，不计算偏差。

### 6.2 自动对齐

`Rack3DLocator.auto_align()` 输出固定结构：

- `coordinate_system`
- `transform_matrix`
- `aligned_pointcloud_token`
- `aligned_preview_image_url`
- `front_view_url`
- `top_view_url`
- `side_view_url`
- `features`：立柱、层线、支撑面等识别信息。

第一阶段可使用单位矩阵和模拟特征，但必须保留可替换算法边界。失败时返回明确错误码：

- `POINTCLOUD_NOT_ENOUGH`
- `COLUMN_NOT_FOUND`
- `LAYER_PLANE_NOT_FOUND`
- `COORDINATE_SYSTEM_FAILED`
- `LOW_CONFIDENCE`

### 6.3 配方查询与 ROI 保存

新增服务方法：

- `get_current_recipe(locate_type, layer_index, rack_type=None)`
- `save_roi(locate_type, layer_index, roi_3d, alignment_token, recipe_id=None)`
- `select_roi(recipe, locate_type, layer_index)`

查询规则：

- `GLOBAL + 0` 查询整体定位配方和全局 ROI。
- `LAYER + 1/2/3` 查询对应层局部定位配方和局部 ROI。
- 局部 ROI 不存在时可返回明确错误；生产定位不静默使用像素 ROI。

### 6.4 定位计算

整体定位：

- 输入整体点云、整体 ROI、自动对齐结果。
- 输出 `overall_offset_x/y/z/rz`、`confidence`、`is_valid`。
- 保存结果并作为后续层定位基准。

分层定位：

- 输入当前层点云、当前层 ROI、最近有效整体定位结果。
- 输出 `layer_offset_x/y/z/rz`。
- 计算最终补偿：

```text
final_offset_x = overall_offset_x + layer_offset_x
final_offset_y = overall_offset_y + layer_offset_y
final_offset_z = overall_offset_z + layer_offset_z
final_offset_rz = overall_offset_rz + layer_offset_rz
```

安全校验：

- ROI 内有效点数不足时 NG。
- 置信度低于 `min_confidence` / `confidence_threshold` 时 NG。
- X/Y/Z/RZ 超过配方容差时 NG。
- NG 时 `compensation_valid=false`，禁止写入有效补偿。

### 6.5 PLC 写入

复用现有 `PlcVisionResultWriter` 和 `apps.devices.adapters.plc.PLCAdapter`。

写入 payload 包含：

- `locate_done`
- `locate_ok`
- `locate_type`
- `layer_index`
- `offset_x/y/z/rz`
- `final_offset_x/y/z/rz`
- `confidence`
- `compensation_valid`
- `error_code`

Mock PLC 保存写入回显，真实 Siemens S7 adapter 继续预留。

## 7. API

新增或补齐正式 API，仍使用统一响应：

```json
{"success": true, "data": {}, "error": ""}
```

### 7.1 相机与采集

- `POST /vision/api/vision/3d/camera/test/`
- `POST /vision/api/vision/3d/capture/`

### 7.2 自动对齐

- `POST /vision/api/vision/3d/align/`
- 旧 `auto-align/` 保留，委托到 `align/`。

### 7.3 配方与 ROI

- `GET /vision/api/vision/3d/recipes/`
- `GET /vision/api/vision/3d/recipes/current/?locate_type=GLOBAL&layer_index=0`
- `POST /vision/api/vision/3d/recipes/save/`
- `GET /vision/api/vision/3d/rois/`
- `POST /vision/api/vision/3d/rois/`

### 7.4 定位与 PLC

- `POST /vision/api/vision/3d/locate/`
- `POST /vision/api/vision/3d/write-plc/`

### 7.5 结果查询

- `GET /vision/api/vision/3d/results/latest/`
- `GET /vision/api/vision/3d/results/`

旧 `/vision/api/rack-location/...` 保留，并返回兼容字段。

## 8. 前端工作台

继续使用 `templates/vision/rack_locator_panel.html` 和 `static/vision/js/rack_locator_workbench.js`。

### 8.1 参数区

补齐：

- `locate_type`：整体定位 / 层定位。
- `layer_index`：0 / 1 / 2 / 3。
- `photo_pose_name`
- `rack_type`
- 当前配方名称。
- 当前 ROI 三维范围。

`layer_index=0` 时自动切到 `GLOBAL`；`layer_index=1/2/3` 时自动切到 `LAYER`。

### 8.2 点云显示区

支持两个模式：

- 原始点云模式：只观察，不允许保存最终 ROI。
- 矫正视图模式：自动对齐成功后展示正视图，允许绘制或编辑三维 ROI。

前端可显示二维投影框，但保存请求必须提交三维 ROI 六参数。

### 8.3 操作状态机

前端状态：

- `idle`
- `captured`
- `aligned`
- `roi_saved`
- `located_ok`
- `located_ng`
- `plc_written`

按钮规则：

- 未采集点云：禁用自动对齐、保存 ROI、计算偏差、写 PLC。
- 未自动对齐成功：禁用保存 ROI。
- 未保存 ROI：禁用计算偏差。
- 定位 NG：禁用写入有效补偿。
- PLC 写入失败：显示错误并保留结果。

### 8.4 结果区

显示：

- X/Y/Z/RZ 偏差。
- 整体偏差、层偏差、最终补偿。
- 置信度。
- OK/NG。
- 错误码和错误描述。
- PLC 写入状态。
- 当前 `locate_type`、`layer_index`、配方名、料架条码。

## 9. 测试策略

采用测试先行。重点测试：

- `locate_type + layer_index` 与 `mode + layer_no` 的映射。
- 当前配方查询 `GLOBAL + 0`、`LAYER + 1/2/3`。
- 保存 ROI 必须是三维 ROI，非法边界拒绝。
- 未自动对齐时保存 ROI 被拒绝。
- 未保存 ROI 时定位被拒绝。
- 整体定位保存 `overall_offset_*`。
- 层定位读取最近有效整体结果并计算 `final_offset_*`。
- NG 结果禁止写入有效 PLC 补偿。
- `/api/vision/3d/results/latest/` 返回最近结果。
- 工作台页面包含 `locate_type`、`layer_index`、三维 ROI、关键按钮禁用逻辑。
- 旧泡棉检测 API 和页面测试继续通过。

## 10. 验收映射

- 相机连接测试：`camera/test/` + 前端按钮。
- 手动采集点云：`capture/`。
- 原始点云显示：采集响应返回预览 URL。
- 自动对齐生成矫正视图：`align/`。
- 未对齐不能保存 ROI：服务层和前端双重校验。
- ROI 保存为三维字段：`RackLocationROI3D`。
- 整体和第 1/2/3 层 ROI：`GLOBAL+0`、`LAYER+1/2/3`。
- 当前配方加载：`recipes/current/`。
- 整体粗定位：`locate_type=GLOBAL`。
- 分层局部定位：`locate_type=LAYER`。
- 最终补偿：`overall + layer`。
- NG 错误展示：`error_code/error_message`。
- 手动写 PLC：`write-plc/`。
- PLC 状态回显：结果 payload 和页面状态。
- 每次定位入库：`RackLocationResult`。
- 不影响旧模块：保留旧模型、旧接口、旧页面入口。

## 11. 涉及文件

- `apps/vision/models.py`
- `apps/vision/migrations/`
- `apps/vision/admin.py`
- `apps/vision/rack_location.py`
- `apps/vision/views.py`
- `apps/vision/urls.py`
- `apps/vision/tests.py`
- `templates/vision/rack_locator_panel.html`
- `static/vision/js/rack_locator_workbench.js`

