# 3D 深度相机料架定位模块 (`apps/vision/rack_3d`)

基于 Provider 设计模式的 3D 料架定位系统，支持 **MOCK**（无硬件模拟）/ **REAL**（真实相机+机器人）双模式。

## 架构

```
RackPositioningService (services.py)  ← 主协调器
 ├─ ProviderFactory (providers.py)
 │   ├─ HandEyeProvider    Mock / Real   T_flange_camera (手眼标定，固定)
 │   ├─ RobotPoseProvider  Mock / Real   T_base_flange   (拍照位姿，每层变)
 │   └─ DepthCameraProvider Mock / Real  点云
 ├─ PointCloudProcessor (processors.py)  坐标转换 / ROI 裁剪 / 滤波 / 下采样
 ├─ PositioningAlgorithm (algorithms.py) Z=RANSAC平面 · Y=前边缘中位数 · X=立柱中位数
 └─ CompensationCalculator (calculators.py) 偏移=实际−理论，补偿/校验/置信度
exceptions.py  统一错误码 + 异常层次
api.py / urls.py  REST 接口 + 工作台页面
```

核心转换公式：`P_base = T_base_flange @ T_flange_camera @ P_camera`
补偿约定：`offset = actual - standard`，`compensation = offset`（默认 sign_convention=1）。

## MOCK 模式（默认，无需硬件）

```bash
# settings.py: RACK_3D_POSITIONING_MODE = 'MOCK'
python manage.py migrate
python manage.py seed_rack_3d_demo --reset --history 2   # 造 3 层 Demo 配方+ROI+历史
python manage.py runserver
# 浏览器打开 /vision/rack-3d/  → 选配方 → 采集点云 → 计算偏差
```

代码调用：

```python
from apps.vision.rack_3d.services import RackPositioningService
result = RackPositioningService(mode='MOCK').execute_positioning(recipe_id, layer_no)
```

## REAL 模式（工厂现场）

1. `settings.py`：`RACK_3D_POSITIONING_MODE = 'REAL'`
2. 完成手眼标定，将 `T_flange_camera` 写入配方关联的 `HandEyeCalibration`（或 `hand_eye_config`）。
3. 提供数据源：
   ```python
   RackPositioningService(
       mode='REAL',
       robot_service=my_robot_service,        # 提供 get_tcp_pose()
       dm_camera_service=my_dm_camera_service, # 提供 capture_frame_data(frame_type='POINTCLOUD')
   )
   ```
   若不接机器人服务，`RealRobotPoseProvider` 回退读取配方 `capture_pose`。
4. 为每层配置机器人基坐标系下的 support/edge/pillar ROI（`RackLocationROI3DEnhanced`）。

Mock→Real 只换数据来源，算法/服务代码不变。

## REST API（前缀 `/vision/rack-3d/`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `recipes/` | 配方列表 |
| GET  | `recipes/<id>/rois/?layer_no=` | 某层 ROI |
| POST | `rois/` | 创建/更新 ROI（校验 min<max） |
| PATCH| `recipes/<id>/coordinates/` | 更新理论坐标 |
| POST | `capture/` | 采集+转换，返回预览点集与边界 |
| POST | `calculate/` | 执行定位（`save` 可选） |
| GET  | `results/?position_no=&layer_no=&limit=` | 历史结果 |

响应：成功 `{"success":true,"data":...}`；失败 `{"success":false,"error":{code,message,details}}`。

```bash
curl -X POST http://127.0.0.1:8000/vision/rack-3d/calculate/ \
  -H "Content-Type: application/json" -d '{"recipe_id":1,"layer_no":2,"save":true}'
```

## 测试

```bash
python manage.py test apps.vision.rack_3d.tests
```

覆盖：Provider / 处理器 / 算法 / 计算器单元测试、MOCK 端到端集成测试、REST API 测试，
并内联验证设计文档的 Property 2/3/5/8/10。

## 说明

- 依赖：numpy、scipy、open3d（缺失时滤波/下采样/RANSAC 自动回退到 NumPy）、opencv。
- 该模块自成一体，不依赖 `rack_location.py` 等旧的并行实现。
