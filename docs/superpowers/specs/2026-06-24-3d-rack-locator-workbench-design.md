# 3D 料架定位交互式工作台 设计文档

日期：2026-06-24
分支：feature/3d-rack-location-module
范围：仅限 3D 料架定位（`apps/vision/` 及其模板/静态资源）。不改动 2D 泡棉检测、PLC、production、workflow。共享文件 `image_io.py` 中只**新增** 3D 专用函数，不修改既有 2D 函数。

## 1. 目标

把 `/vision/rack-locator/` 工作台改造成与 2D `/vision/foam-inspector/` 同构的双栏交互界面：

- 顶部：选择配方（POS / 层号可编辑）。
- 左栏：显示 3D 点云伪彩图，可在图上拖拽绘制 ROI；按钮「采集点云」「计算偏差」。
- 右栏：显示带 ROI 框的点云计算结果图 + X/Y/Z/Rz 偏差 + 置信度 + OK/NG 判定 + 「保存结果到数据库」按钮。
- 次级区块（保留）：原有「按 POS/层号自动拍照计算」按钮 + 最近定位历史表。

业务区别于 2D：2D 判断泡棉是否存在；3D 计算坐标偏差。现阶段只做手动现场调试，自动化（与 PLC 交互）后续再接入，本期不调用 PLC。

## 2. 后端

在 `RackLocationService` 新增三个方法，配套三个视图与路由：

- **`capture_workbench(recipe_id)`**：通过 `DMCameraRackFrameProvider` 采集（真实 LWP-D322W 相机，离线时回退到模拟场景）。把*组织化点云*持久化到 `media/vision/rack_workbench/<stamp>.npy`，渲染与之像素一一对应的伪彩预览 PNG，返回 `{preview_image_url, pointcloud_token, image_width, image_height, source}`。预览图由同一点云数组着色，保证 ROI 像素坐标与点云格点 1:1 对应。
- **`calculate_workbench(token, roi, recipe_id, ...)`**：读取持久化的 `.npy`，按绘制的 ROI 裁剪，复用既有 `RackPoseEstimator` 计算 actual XYZ / 偏差 / 置信度 / OK-NG，并渲染带框标注结果图。**仅预览，不写库。** 返回偏差 + `result_image_url`。
- **`save_workbench_result(token, roi, recipe_id, position_no, layer_no)`**：用同一 `.npy` 重新执行确定性计算（避免被前端篡改的数值入库），写入 `VisionTask` + `RackLocationResult` + `VisionImage`，复用 `trigger()` 的持久化模式。**不调用 PLC。**

路由（仅 vision）：
- `POST api/rack-location/workbench/capture/`
- `POST api/rack-location/workbench/calculate/`
- `POST api/rack-location/workbench/save/`

配方下拉、自动触发、历史表沿用既有端点（`api_rack_location_recipes` / `api_rack_location_trigger` / `api_rack_location_results`），不改动。

### image_io 新增（3D 专用，附加）
- `pointcloud_to_preview(pointcloud)`：组织化点云 → 伪彩 BGR 图（按 Z 通道着色）。
- `annotate_pointcloud_roi(preview, roi, output)`：在预览图上画 ROI 框 + 偏差箭头 + 置信度/坐标文字。

## 3. 数据流

选择配方 → 「采集点云」（采集+持久化+预览）→ 拖拽 ROI → 「计算偏差」（裁剪+计算+标注，预览）→ 「保存结果到数据库」（写一行记录，刷新历史）。次级自动路径 = 既有 `trigger`。

## 4. 错误处理

- 未绘制 ROI → 400「请先绘制 ROI」。
- token 缺失 / npy 失效 → 400「点云数据已失效，请重新采集」。
- 采集与回退都失败 → JSON error，状态栏提示。
- 置信度不足 / 偏差超限 → NG 判定 + 既有 estimator 文案。

## 5. 测试（`apps/vision/tests.py`，附加）

- 回退路径下 `capture_workbench` 返回 token + 预览。
- `calculate_workbench` 裁剪持久化 npy，返回偏差 + 结果图。
- `save_workbench_result` 恰好创建一条 `RackLocationResult`。

## 6. 涉及文件（均属 3D 范围）

- `apps/vision/rack_location.py`（新增服务方法）
- `apps/vision/algorithms/image_io.py`（附加 3D 专用 helper）
- `apps/vision/views.py`（3 个新视图）
- `apps/vision/urls.py`（3 条新路由）
- `templates/vision/rack_locator_panel.html`（重写为双栏交互）
- `static/vision/js/rack_locator_workbench.js`（新增）
- `apps/vision/tests.py`（新增测试）
