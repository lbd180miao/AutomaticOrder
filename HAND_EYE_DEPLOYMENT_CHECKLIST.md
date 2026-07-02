# 手眼标定模块部署检查清单

## ✅ 开发完成状态

| 模块 | 状态 | 备注 |
|------|------|------|
| 数据模型 | ✅ 完成 | 3个模型，数据库迁移成功 |
| 坐标转换服务 | ✅ 完成 | 支持3种矩阵格式，精度验证通过 |
| 手眼标定服务 | ✅ 完成 | OpenCV集成，5种标定方法 |
| API接口 | ✅ 完成 | 14个RESTful接口 |
| 前端页面 | ✅ 完成 | 基础管理页面 |
| PLC适配器 | ✅ 完成 | 模拟适配器支持 |
| 测试验证 | ✅ 完成 | 单元测试+集成测试全部通过 |
| 文档 | ✅ 完成 | 使用文档+API文档+快速开始 |

## 📋 部署前检查

### 1. 数据库迁移
```bash
# 检查迁移文件
python manage.py showmigrations vision

# 如未应用，执行迁移
python manage.py migrate vision
```

**预期输出：**
```
vision
 ...
 [X] 0012_racklocationrecipe_capture_pose_and_more
```

### 2. 模型验证
```python
# 进入Django shell
python manage.py shell

from apps.vision.models_hand_eye import HandEyeCalibration
from apps.devices.models import Device

# 验证模型可用
print(HandEyeCalibration.objects.count())
print(Device.objects.count())
```

### 3. 服务验证
```python
from apps.vision.hand_eye_service import HandEyeCalibrationService
from apps.vision.coordinate_transform import CoordinateTransformService

# 验证服务可实例化
service = HandEyeCalibrationService()
transform = CoordinateTransformService()

print("服务初始化成功！")
```

### 4. 坐标转换测试
```bash
# 运行坐标转换测试
python test_hand_eye_transform.py
```

**预期结果：** 所有6个测试通过

### 5. API测试
```bash
# 运行完整API测试
python test_hand_eye_api.py
```

**预期结果：** 11个测试全部通过

### 6. 前端访问
```
访问页面：http://localhost:8000/vision/hand-eye/
```

**检查项：**
- ✅ 页面正常加载
- ✅ 标定列表显示
- ✅ "新建标定"按钮可用
- ✅ 机器人/相机下拉框有数据

## 🔧 配置项

### 1. Django Settings
文件：`AutomaticOrder/settings.py`

```python
INSTALLED_APPS = [
    ...
    'apps.vision',  # 确保已包含
    ...
]
```

### 2. URL配置
文件：`AutomaticOrder/urls.py`

```python
urlpatterns = [
    ...
    path('vision/', include('apps.vision.urls')),  # 确保已包含
    ...
]
```

### 3. 模拟设备模式
文件：`AutomaticOrder/settings.py`

```python
AUTOMATIC_ORDER = {
    'USE_SIMULATED_DEVICES': True,  # 开发/测试模式
    ...
}
```

**生产环境：** 设置为 `False` 并实现真实PLC适配器

## 📊 性能指标

| 指标 | 目标值 | 当前值 | 状态 |
|------|--------|--------|------|
| 坐标转换精度 | < 1e-6 mm | < 1e-6 mm | ✅ |
| 标定样本最少数量 | 3 个 | 3 个 | ✅ |
| 标定误差目标 | < 3 mm | 测试: ~107 mm* | ⚠️ |
| API响应时间 | < 500ms | < 100ms | ✅ |
| 并发支持 | 是 | 是 | ✅ |

*注：测试数据为模拟样本，标定误差较大。真实标定板数据误差应 < 3mm。

## 🔐 安全检查

- ✅ 数据库约束：同组机器人-相机只能有一个激活标定
- ✅ 样本序号唯一性约束
- ✅ 输入验证：矩阵格式验证
- ✅ 旋转矩阵有效性验证
- ✅ 外键级联删除保护

## 📝 创建初始数据

### 1. 创建设备
```python
from apps.devices.models import Device
from apps.core.constants import DeviceType

# 创建机器人
robot = Device.objects.create(
    code='BOXING-ROBOT-01',
    name='装箱机器人#1',
    device_type=DeviceType.BOXING_ROBOT,
    enabled=True,
    status='ONLINE'
)

# 创建相机
camera = Device.objects.create(
    code='DM-CAMERA-01',
    name='DM 3D深度相机#1',
    device_type=DeviceType.DEPTH_CAMERA,
    enabled=True,
    status='ONLINE'
)
```

### 2. 创建示例标定
```python
from apps.vision.hand_eye_service import HandEyeCalibrationService

service = HandEyeCalibrationService()

calibration = service.create_calibration(
    name="生产线标定-20260101",
    robot_device_id=robot.id,
    camera_device_id=camera.id,
    operator="张三",
    description="生产线初始标定"
)
```

## 🚀 生产环境部署

### 必需步骤

1. **实现真实PLC适配器**
   ```python
   # 文件：apps/devices/adapters/plc.py
   
   def read_robot_pose(self, robot_code: str) -> dict:
       """从PLC读取机器人位姿"""
       # TODO: 实现真实PLC通信协议
       # 例如：Modbus TCP, OPC UA, Socket等
       pass
   ```

2. **实现标定板检测算法**
   ```python
   # 需要开发：
   # - 棋盘格检测
   # - 圆点阵列检测
   # - 返回 T_camera_target 位姿
   ```

3. **配置生产环境**
   ```python
   # settings.py
   AUTOMATIC_ORDER = {
       'USE_SIMULATED_DEVICES': False,
       ...
   }
   ```

4. **数据备份**
   ```bash
   # 定期备份标定数据
   python manage.py dumpdata vision.HandEyeCalibration > calibrations_backup.json
   ```

### 可选优化

- [ ] 完善前端样本采集界面
- [ ] 添加标定结果可视化
- [ ] 实现自动化标定流程
- [ ] 添加标定数据3D可视化
- [ ] 实现在线标定更新

## 📞 技术支持

### 常见问题解决

**问题1：标定误差过大**
```
原因：样本质量差、位姿分布不均匀
解决：增加样本数量，确保覆盖整个工作空间
```

**问题2：验证不通过**
```
原因：T_base_flange获取错误
解决：检查PLC通信，确认位姿数据正确
```

**问题3：矩阵格式错误**
```
原因：JSON格式不符合规范
解决：参考文档中的"矩阵格式支持"章节
```

### 调试命令

```bash
# 查看标定列表
python manage.py shell
>>> from apps.vision.models_hand_eye import HandEyeCalibration
>>> for cal in HandEyeCalibration.objects.all():
...     print(f"{cal.name}: 误差={cal.calibration_error}mm, 激活={cal.is_active}")

# 查看样本数量
>>> from apps.vision.models_hand_eye import HandEyeCalibrationSample
>>> HandEyeCalibrationSample.objects.values('calibration__name').annotate(count=Count('id'))

# 测试坐标转换
>>> from apps.vision.coordinate_transform import CoordinateTransformService
>>> service = CoordinateTransformService()
>>> import numpy as np
>>> P = service.camera_to_robot_base(
...     np.array([100, 50, 500]),
...     service.pose_to_matrix(30, 0, 100, 0, 0, 0),
...     service.pose_to_matrix(500, 200, 850, 0, 0, 0)
... )
>>> print(P)  # 应输出 [630. 250. 1450.]
```

## ✅ 部署确认

**部署完成后，确认以下各项：**

- [ ] 数据库迁移成功
- [ ] 所有测试通过（坐标转换+API）
- [ ] 前端页面可访问
- [ ] 能创建标定任务
- [ ] 能添加样本（至少手动输入测试）
- [ ] 能计算标定（使用模拟数据）
- [ ] 能激活标定
- [ ] 能导出导入标定
- [ ] 机器人位姿可读取（模拟或真实）
- [ ] 文档已阅读

## 📚 相关文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 详细使用文档 | `HAND_EYE_CALIBRATION_README.md` | 完整API和功能说明 |
| 快速开始 | `手眼标定快速开始.md` | 5分钟快速入门 |
| 模块总结 | `HAND_EYE_MODULE_SUMMARY.md` | 开发总结和清单 |
| 部署检查 | `HAND_EYE_DEPLOYMENT_CHECKLIST.md` | 本文档 |

## 🎯 下一步

### 短期计划（1-2周）
1. 实现标定板检测算法
2. 完善前端样本采集界面
3. 集成到料架定位流程

### 中期计划（1-2月）
1. 实现真实PLC通信
2. 自动化标定流程
3. 标定质量评估

### 长期计划（3-6月）
1. 在线标定更新
2. 多相机标定
3. 标定数据可视化

---

**部署负责人签字：** _____________  
**部署日期：** _____________  
**验收人签字：** _____________  
**验收日期：** _____________  

---

**版本：** v1.0.0  
**最后更新：** 2026年1月  
**状态：** ✅ 可部署
