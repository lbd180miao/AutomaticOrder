# 3D 料架定位模块重构设计文档

日期：2026-06-25
分支：feature/3d-rack-location-module
范围：在现有 `apps/vision` 3D 料架定位工作台基础上重构。保留旧 `api/rack-location/...` 兼容入口，新增正式 `/api/vision/3d/...` API。只处理 3D 深度相机料架定位，不改 2D 泡棉检测业务。

## 1. 背景与决策

现有项目已经具备 3D 料架定位基础能力：`RackLocationRecipe`、`RackLocationResult`、`RackLocationService`、点云工作台、模拟点云回退、计算结果入库、PLC 写入入口。当前主要缺口是 ROI 仍以 `roi_config.target_roi` 的二维图像框语义为主，不能清晰表达料架坐标系下的三维空间 ROI。

本次采用“方案 1 + 少量方案 2”：在原有 3D 工作台基础上重构，同时新增 `/api/vision/3d/...` 作为正式接口。旧接口继续可用并委托到新服务层，避免破坏已有页面、历史数据和测试。

## 2. 目标

- 支持左料架、右料架分别建立 3D 定位配方。
- 支持每个配方配置全局 ROI，以及第 1、2、3 层局部 ROI。
- ROI 以料架坐标系三维空间盒保存：`x_min/x_max/y_min/y_max/z_min/z_max`。
- 支持 3D 相机采集原始 RGB、深度图、点云，并生成矫正后的正视、俯视、侧视与点云预览。
- 支持基于三维 ROI 裁剪点云，计算 X/Y/Z/Rz 补偿值、置信度和 OK/NG。
- 支持测试定位不强制先保存 ROI，便于现场调试。
- 支持生产入口按 `rack_side + layer_no` 自动加载对应 ROI 配方。
- 支持将定位结果写入 PLC，payload 包含定位完成、OK/NG、X/Y/Z/Rz 和置信度。

## 3. 非目标

- 不重构 2D 泡棉检测模块。
- 不删除旧 `roi_config.target_roi` 字段。
- 不强制接入真实 3D 点云算法；第一阶段允许使用可替换的模拟姿态识别、单位变换和投影视图生成。
- 不变更 production、workflow、MES 等无关模块的主流程。

## 4. 架构

继续使用 `apps/vision` 作为 3D 料架定位模块归属。新增正式门面 `Rack3DLocator`，保留 `RackLocationService` 作为兼容服务和旧视图调用入口。

```text
3D 工作台 / 生产触发 / API
  -> /api/vision/3d/... 正式接口
  -> Rack3DLocator
     -> 相机帧提供者：真实 DM 相机优先，失败回退模拟点云
     -> 姿态识别：立柱、层板、支撑面、料架坐标系
     -> 视图生成：原始图、深度图、正视图、俯视图、侧视图、裁剪预览
     -> 三维 ROI 裁剪
     -> 偏差计算
     -> PLC 写入

旧 api/rack-location/...
  -> RackLocationService
  -> Rack3DLocator
```

旧接口保留兼容，正式功能优先在 `/api/vision/3d/...` 暴露。

## 5. 数据模型

### 5.1 3D 定位配方

继续使用 `RackLocationRecipe` 作为主配方表，保留现有字段并强化语义：

- `recipe_name`
- `rack_side`：`LEFT` / `RIGHT` / `BOTH`，正式生产配置优先使用左右料架。
- `rack_type`
- `position_no`
- `layer_count`
- `layer_no`
- `camera_device`
- `camera_config`
- `standard_x/standard_y/standard_z/standard_rz`
- `max_offset_x/max_offset_y/max_offset_z/max_offset_rz`
- `confidence_threshold`
- `hand_eye_config`
- `enabled`

### 5.2 新增三维 ROI 配方

新增模型 `RackLocationROI3D`：

```text
id
recipe_id
roi_name
mode                  # global / local
layer_no              # global 可为空，local 为 1 / 2 / 3
coordinate_system     # rack
x_min
x_max
y_min
y_max
z_min
z_max
enabled
created_at
updated_at
```

约束与规则：

- `x_min < x_max`，`y_min < y_max`，`z_min < z_max`。
- 同一配方下可有一个启用的 `global` ROI。
- 同一配方下每个 `layer_no` 可有一个启用的 `local` ROI。
- 生产定位优先使用对应层局部 ROI；没有局部 ROI 时允许回退全局 ROI；仍没有 ROI 时返回 NG。

### 5.3 定位结果

继续使用 `RackLocationResult`，保留：

- `side`
- `position_no`
- `layer_no`
- `offset_x/offset_y/offset_z/offset_rz`
- `actual_x/actual_y/actual_z`
- `confidence`
- `is_success`
- `error_code`
- `error_message`
- `raw_data_path`
- `result_image_path`
- `plc_write_status`
- `plc_error_message`
- `result_data`

`result_data` 记录 `roi_id`、`roi_source`、`coordinate_system`、`point_count`、`plc_payload` 和算法来源，便于追溯。

## 6. 服务层设计

新增 `Rack3DLocator`，核心方法：

```python
capture()
auto_align(point_cloud)
build_rack_coordinate_system(point_cloud)
generate_corrected_views(alignment)
crop_point_cloud_by_roi(point_cloud, roi_3d)
calculate_offset(cropped_cloud, recipe, layer_no)
locate(rack_side, layer_no, recipe_id=None)
write_result_to_plc(result)
```

第一阶段实现方式：

- `capture()` 优先调用现有 DM 相机服务；失败时回退 `build_sample_pointcloud()`。
- `auto_align()` 返回可替换的姿态识别结果，包括料架坐标系、支撑面、立柱和层板识别信息。
- `build_rack_coordinate_system()` 第一阶段可使用单位矩阵或模拟变换，但输出结构固定。
- `generate_corrected_views()` 生成正视、俯视、侧视、点云预览图 URL。
- `crop_point_cloud_by_roi()` 按三维空间边界过滤点云。
- `calculate_offset()` 以裁剪点云中位数或支撑面中心计算实际坐标，再与配方标准位置比较。
- `locate()` 自动选择配方和 ROI，完成采集、裁剪、计算、结果入库。
- `write_result_to_plc()` 复用现有 `PlcVisionResultWriter`，并保持写入前二次校验。

兼容策略：

- `RackLocationService.capture_workbench()`、`calculate_workbench()`、`save_workbench_result()` 保留。
- 旧二维 `target_roi` 只作为预览图辅助框和历史兼容输入。
- 新保存流程写入 `RackLocationROI3D`。
- 旧配方只有 `target_roi` 时仍可测试定位，响应中标记 `roi_source: legacy_target_roi`。

## 7. API 设计

正式 API 使用统一响应结构：

```json
{
  "success": true,
  "data": {},
  "error": ""
}
```

### 7.1 配方 API

```text
GET    /api/vision/3d/recipes/
POST   /api/vision/3d/recipes/
GET    /api/vision/3d/recipes/{id}/
PUT    /api/vision/3d/recipes/{id}/
```

### 7.2 ROI API

```text
GET    /api/vision/3d/rois/?recipe_id=xxx
POST   /api/vision/3d/rois/
PUT    /api/vision/3d/rois/{id}/
```

### 7.3 定位动作 API

```text
POST   /api/vision/3d/capture/
POST   /api/vision/3d/auto-align/
POST   /api/vision/3d/test-locate/
POST   /api/vision/3d/write-plc/
```

行为：

- `capture` 返回 RGB 图、深度图、点云 token、原始点云预览。
- `auto-align` 返回料架坐标系、识别特征、矫正视图 URL。
- `test-locate` 接收当前三维 ROI 参数，可不先保存，返回偏差和裁剪预览。
- `write-plc` 根据结果 ID 或当前测试结果写入 PLC。

## 8. 前端工作台设计

页面继续使用 `3D 料架定位工作台`，布局为左右两栏。

左侧图像与点云区域：

- 原始 RGB 图。
- 原始深度图。
- 原始点云预览。
- 矫正后的正视图。
- 矫正后的俯视图。
- 矫正后的侧视图。
- 裁剪后点云预览。

右侧参数与结果区域：

- 料架侧别：左料架 / 右料架。
- 定位模式：全局定位 / 局部定位。
- 层号：第 1 / 2 / 3 层。
- 三维 ROI 参数：`X_min/X_max/Y_min/Y_max/Z_min/Z_max`。
- 操作按钮：采集 3D 图像、自动识别料架姿态、生成矫正视图、测试定位、保存 ROI 配方、写入 PLC。
- 结果显示：X/Y/Z/Rz 补偿、置信度、OK/NG、错误信息。

交互规则：

- 原始图只用于观察。
- 矫正视图用于辅助配置 ROI。
- 用户可在矫正视图拖拽辅助区域，前端预填三维 ROI 参数。
- 用户可直接编辑六个 ROI 数值，便于现场精调。
- 测试定位使用当前页面 ROI 参数。
- 保存 ROI 后写入 `RackLocationROI3D`。
- 生产定位按料架侧别和层号自动加载对应 ROI。

## 9. 错误处理

- 未采集点云：HTTP 400，`请先采集 3D 图像`。
- 未完成姿态识别：HTTP 400，`请先识别料架姿态`。
- ROI 参数缺失或边界非法：HTTP 400，`三维 ROI 参数无效`。
- ROI 内有效点太少：定位 NG，`error_code=POINTCLOUD_EMPTY`。
- 未找到对应 ROI：定位 NG，`error_code=ROI_NOT_CONFIGURED`。
- 置信度不足：定位 NG，`error_code=LOW_CONFIDENCE`。
- 补偿超限：定位 NG，`error_code=OFFSET_OUT_OF_RANGE`。
- PLC 写入失败：保留定位结果，`plc_write_status=FAILED`。

## 10. 测试策略

采用测试先行。主要测试：

- `RackLocationROI3D` 可保存全局 ROI 和第 1、2、3 层局部 ROI。
- ROI 边界校验拒绝 `min >= max`。
- 三维 ROI 裁剪只保留空间盒内点。
- `test-locate` 使用当前请求 ROI，不要求先保存。
- `locate(rack_side, layer_no)` 自动加载对应 ROI。
- 没有局部 ROI 时回退全局 ROI。
- `/api/vision/3d/recipes/` 创建、列表、详情、更新正常。
- `/api/vision/3d/rois/` 创建、列表、更新正常。
- `/api/vision/3d/capture/auto-align/test-locate/write-plc/` 返回统一结构。
- 旧 `/api/rack-location/...` 兼容接口仍可采集、计算、保存、写 PLC。
- 页面包含三维 ROI 六参数、料架侧别、定位模式、层号、关键按钮和结果字段。

## 11. 验收映射

- 左右料架配方：`RackLocationRecipe.rack_side` + `/api/vision/3d/recipes/`。
- 全局 ROI：`RackLocationROI3D.mode=global`。
- 三层局部 ROI：`RackLocationROI3D.mode=local` + `layer_no=1/2/3`。
- 三维参数持久化：`x_min/x_max/y_min/y_max/z_min/z_max` 字段。
- 原始图和矫正图显示：`capture` + `auto-align` 返回图像 URL。
- 测试定位返回补偿：`/api/vision/3d/test-locate/`。
- 保存 ROI 持久化：`/api/vision/3d/rois/`。
- 写入 PLC：`/api/vision/3d/write-plc/`。
- 生产自动加载 ROI：`Rack3DLocator.locate(rack_side, layer_no)`。
- 后续真实 SDK 与算法接入：相机帧提供者、姿态识别、点云裁剪、PLC writer 均有独立边界。

## 12. 涉及文件

- `apps/vision/models.py`
- `apps/vision/migrations/`
- `apps/vision/admin.py`
- `apps/vision/rack_location.py`
- `apps/vision/views.py`
- `apps/vision/urls.py`
- `apps/vision/tests.py`
- `templates/vision/rack_locator_panel.html`
- `static/vision/js/rack_locator_workbench.js`
- `templates/vision/rack_location_recipes.html`
- `templates/vision/rack_location_recipe_form.html`
