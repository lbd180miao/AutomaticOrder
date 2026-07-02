# 手眼标定模块使用指南

## 概述

手眼标定模块实现了3D深度相机与机器人之间的坐标转换功能，核心公式为：

```
P_base = T_base_flange × T_flange_camera × P_camera
```

**转换流程：**
1. 相机坐标系点 `P_camera`
2. 通过 `T_flange_camera`（手眼标定矩阵）→ 机器人法兰坐标系
3. 通过 `T_base_flange`（机器人当前位姿）→ 机器人基坐标系
4. 得到机器人基坐标系点 `P_base`

## 核心概念

### 1. T_flange_camera（手眼标定矩阵）
- **特点**：标定完成后固定不变
- **用途**：描述相机与机器人法兰之间的固定几何关系
- **格式**：4×4 齐次变换矩阵
- **获取方式**：通过 OpenCV calibrateHandEye 或厂商工具计算

### 2. T_base_flange（机器人位姿）
- **特点**：每次机器人移动都会变化
- **用途**：描述机器人法兰在基坐标系的当前位置
- **格式**：4×4 矩阵 或 六自由度 {x, y, z, rx, ry, rz}
- **获取方式**：从PLC实时读取机器人控制器反馈

## 数据库模型

### HandEyeCalibration（手眼标定）
```python
- name: 标定名称（唯一）
- robot_device: 关联的机器人设备
- camera_device: 关联的相机设备
- T_flange_camera: 手眼标定矩阵（JSON）
- calibration_error: 标定误差（mm）
- sample_count: 标定样本数量
- calibration_method: 标定方法（OPENCV_TSAI等）
- is_active: 是否激活（同一组机器人-相机只能有一个激活）
- verified_at: 验证时间
```

### HandEyeCalibrationSample（标定样本）
```python
- calibration: 所属标定任务
- sample_index: 样本序号
- T_base_flange: 机器人位姿（采样时）
- T_camera_target: 标定板在相机坐标系的位姿
- detection_success: 检测是否成功
- reprojection_error: 重投影误差
```

### HandEyeVerificationResult（验证结果）
```python
- calibration: 所属标定任务
- test_points_camera: 相机坐标系测试点
- test_points_robot: 转换后的机器人坐标系点
- mean_error: 平均误差
- is_passed: 是否通过验证
```

## 使用流程

### 1. 创建标定任务

**前端页面：** `/vision/hand-eye/`

**API：**
```python
POST /vision/api/hand-eye/calibrations/create/
{
    "name": "装箱机器人-DM相机-20260101",
    "robot_device_id": 1,
    "camera_device_id": 2,
    "operator": "张三",
    "description": "第一次标定"
}
```

**Python代码：**
```python
from apps.vision.hand_eye_service import HandEyeCalibrationService

service = HandEyeCalibrationService()
calibration = service.create_calibration(
    name="装箱机器人-DM相机-20260101",
    robot_device_id=1,
    camera_device_id=2,
    operator="张三"
)
```

### 2. 采集标定样本

**要求：**
- 至少 3 个样本（建议 10-15 个）
- 不同的机器人位姿（覆盖工作空间）
- 每个位姿记录：机器人位姿 + 标定板在相机中的位姿

**API：**
```python
POST /vision/api/hand-eye/calibrations/{id}/samples/add/
{
    "T_base_flange": {
        "x": 500, "y": 200, "z": 850,
        "rx": 0, "ry": 0, "rz": 0
    },
    "T_camera_target": {
        "rvec": [0.1, 0.2, 0.3],
        "tvec": [100, 50, 600]
    }
}
```

**Python代码：**
```python
# 从PLC读取机器人位姿
robot_pose = device_service.adapter.read_robot_pose('ROBOT-01')

# 从相机检测标定板位姿（需实现标定板检测算法）
target_pose = detect_calibration_target()

# 添加样本
service.add_sample(
    calibration_id=1,
    T_base_flange=robot_pose['pose'],
    T_camera_target=target_pose
)
```

### 3. 计算标定

**API：**
```python
POST /vision/api/hand-eye/calibrations/{id}/compute/
{
    "method": "OPENCV_TSAI"
}
```

**Python代码：**
```python
result = service.compute_calibration(
    calibration_id=1,
    method='OPENCV_TSAI'
)
print(f"标定完成，误差: {result['calibration_error']:.4f} mm")
```

**支持的方法：**
- `OPENCV_TSAI`：Tsai-Lenz方法（推荐）
- `OPENCV_PARK`：Park方法
- `OPENCV_HORAUD`：Horaud方法
- `OPENCV_ANDREFF`：Andreff方法
- `OPENCV_DANIILIDIS`：Daniilidis方法

### 4. 验证标定

**API：**
```python
POST /vision/api/hand-eye/calibrations/{id}/verify/
{
    "T_base_flange": {"x": 500, "y": 200, "z": 850, ...},
    "test_points_camera": [[100, 50, 500], [200, 100, 500]],
    "ground_truth_points": [[630, 250, 1450], [730, 300, 1450]],
    "error_threshold": 5.0
}
```

**Python代码：**
```python
verification = service.verify_calibration(
    calibration_id=1,
    T_base_flange=robot_pose,
    test_points_camera=[[100, 50, 500]],
    ground_truth_points=[[630, 250, 1450]],
    error_threshold=5.0
)
print(f"验证{'通过' if verification.is_passed else '失败'}")
```

### 5. 激活标定

**API：**
```python
POST /vision/api/hand-eye/calibrations/{id}/activate/
```

**Python代码：**
```python
service.activate_calibration(calibration_id=1)
```

### 6. 在生产中使用

**集成到料架定位流程：**
```python
from apps.vision.coordinate_transform import CoordinateTransformService
from apps.vision.models_hand_eye import HandEyeCalibration

# 1. 获取激活的标定配置
calibration = HandEyeCalibration.objects.filter(
    robot_device=robot,
    camera_device=camera,
    is_active=True
).first()

# 2. 解析手眼标定矩阵
transform_service = CoordinateTransformService()
T_flange_camera = transform_service.parse_matrix_from_json(
    calibration.T_flange_camera
)

# 3. 获取机器人当前位姿
robot_pose = device_service.adapter.read_robot_pose('ROBOT-01')
T_base_flange = transform_service.parse_matrix_from_json(robot_pose['pose'])

# 4. 采集点云（相机坐标系）
frame_data = dm_camera_service.capture_frame_data('POINTCLOUD')
P_camera = frame_data['data']  # (N, 3) numpy数组

# 5. 坐标转换
P_base = transform_service.camera_to_robot_base(
    P_camera, T_flange_camera, T_base_flange
)

# 6. 后续处理（ROI裁剪、特征提取等）在机器人坐标系下进行
# ...
```

## API 接口总览

### 标定管理
- `GET /vision/api/hand-eye/calibrations/` - 获取标定列表
- `POST /vision/api/hand-eye/calibrations/create/` - 创建标定
- `GET /vision/api/hand-eye/calibrations/{id}/` - 获取标定详情
- `PUT /vision/api/hand-eye/calibrations/{id}/update/` - 更新标定
- `DELETE /vision/api/hand-eye/calibrations/{id}/delete/` - 删除标定

### 样本管理
- `GET /vision/api/hand-eye/calibrations/{id}/samples/` - 获取样本列表
- `POST /vision/api/hand-eye/calibrations/{id}/samples/add/` - 添加样本
- `DELETE /vision/api/hand-eye/samples/{sample_id}/delete/` - 删除样本
- `POST /vision/api/hand-eye/calibrations/{id}/samples/clear/` - 清空样本

### 标定计算
- `POST /vision/api/hand-eye/calibrations/{id}/compute/` - 计算标定
- `POST /vision/api/hand-eye/calibrations/{id}/activate/` - 激活标定

### 验证
- `POST /vision/api/hand-eye/calibrations/{id}/verify/` - 验证标定
- `GET /vision/api/hand-eye/calibrations/{id}/verifications/` - 获取验证记录

### 辅助接口
- `POST /vision/api/hand-eye/robot-pose/` - 获取机器人位姿
- `POST /vision/api/hand-eye/transform-test/` - 测试坐标转换
- `GET /vision/api/hand-eye/calibrations/{id}/export/` - 导出标定
- `POST /vision/api/hand-eye/calibrations/import/` - 导入标定

## 矩阵格式支持

### 六自由度格式（推荐用于PLC通信）
```json
{
    "x": 500.0,
    "y": 200.0,
    "z": 850.0,
    "rx": 0.0,
    "ry": 0.0,
    "rz": 90.0
}
```

### 4×4 矩阵格式
```json
{
    "matrix": [
        [1, 0, 0, 500],
        [0, 1, 0, 200],
        [0, 0, 1, 850],
        [0, 0, 0, 1]
    ]
}
```

### OpenCV 格式
```json
{
    "rvec": [0, 0, 1.5708],
    "tvec": [500, 200, 850]
}
```

## 测试

运行测试脚本验证坐标转换功能：
```bash
python test_hand_eye_transform.py
```

测试包括：
1. 单位矩阵转换
2. 纯平移变换
3. 旋转+平移变换
4. 点云批量转换
5. 矩阵格式解析
6. 坐标转换验证

## 注意事项

1. **标定样本质量**：
   - 样本数量：建议 10-15 个
   - 位姿分布：覆盖整个工作空间
   - 检测精度：确保标定板特征点准确检测

2. **标定误差**：
   - < 1mm：优秀
   - 1-3mm：良好
   - > 3mm：需要重新标定

3. **验证通过标准**：
   - 平均误差 < 5mm
   - 最大误差 < 10mm

4. **坐标系约定**：
   - 右手坐标系
   - 欧拉角顺序：ZYX
   - 角度单位：度（API）/ 弧度（内部计算）
   - 距离单位：毫米（mm）

5. **并发问题**：
   - 同一组机器人-相机只能有一个激活的标定
   - 数据库约束自动保证唯一性

6. **PLC通信**：
   - 模拟模式：返回固定的模拟位姿
   - 生产模式：需实现具体PLC协议

## 故障排查

### 标定误差过大
- 检查标定板检测精度
- 增加样本数量
- 确保位姿分布均匀
- 尝试不同的标定方法

### 验证不通过
- 检查T_base_flange是否正确获取
- 检查测试点是否在有效范围内
- 检查期望值计算是否正确

### 矩阵格式错误
- 使用 `parse_matrix_from_json` 解析前验证格式
- 参考上述"矩阵格式支持"章节

## 下一步开发

1. **标定板检测算法**：实现棋盘格/圆点阵列检测
2. **自动化标定流程**：机器人自动移动到预设位姿采样
3. **标定质量评估**：可视化标定残差分布
4. **标定数据可视化**：3D显示标定样本空间分布
5. **在线标定更新**：运行中持续优化标定参数

## 参考资料

- OpenCV Hand-Eye Calibration: https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html#gaebfc1c9f7434196a374c382abf43439b
- Tsai-Lenz方法论文: "A new technique for fully autonomous and efficient 3D robotics hand/eye calibration"
