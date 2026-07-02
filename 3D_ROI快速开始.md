# 3D ROI配方模块 - 快速开始指南

## 🚀 5分钟快速上手

### 步骤1：创建第一个ROI配方

```python
from apps.vision.roi_3d_service import ROI3DService
from apps.vision.models import RackLocationRecipe

# 初始化服务
service = ROI3DService()

# 假设已有配方 recipe_id=1

# 为第1层批量创建标准ROI（推荐方式）
rois = service.batch_create_layer_rois(
    recipe_id=1,
    layer_no=1,
    position_no=1
)

print(f"✓ 成功创建 {len(rois)} 个ROI")
# 输出: ✓ 成功创建 4 个ROI
```

这将自动创建4种ROI：
- ✅ 主定位ROI - 整体定位
- ✅ 支撑面ROI - 计算Z偏移
- ✅ 前边缘ROI - 计算Y偏移
- ✅ 立柱ROI - 计算X偏移

### 步骤2：使用ROI裁剪点云

```python
import numpy as np

# 假设已有点云数据（机器人坐标系）
pointcloud = np.array([
    [10.5, 20.3, 880.2],
    [15.2, 25.1, 882.5],
    # ... 更多点
])  # shape: (N, 3)

# 裁剪第1层的点云
cropped = service.crop_pointcloud_by_layer(
    pointcloud=pointcloud,
    recipe_id=1,
    layer_no=1
)

# 获取各类型ROI的点云
main_cloud = cropped['main']              # 主ROI点云
support_cloud = cropped['support_plane']  # 支撑面点云
front_cloud = cropped['front_edge']       # 前边缘点云
pillar_cloud = cropped['pillar']          # 立柱点云

print(f"主ROI: {main_cloud.shape[0]} 点")
print(f"支撑面: {support_cloud.shape[0]} 点")
print(f"前边缘: {front_cloud.shape[0]} 点")
print(f"立柱: {pillar_cloud.shape[0]} 点")
```

### 步骤3：查看ROI配置

```python
# 获取第1层的ROI汇总
summary = service.get_layer_roi_summary(recipe_id=1, layer_no=1)

print(f"第{summary['layer_no']}层 - 共{summary['total_rois']}个ROI")
print(f"主ROI: {summary['main_roi'].roi_name}")
print(f"  范围: X[{summary['main_roi'].x_min}, {summary['main_roi'].x_max}]")
print(f"  范围: Y[{summary['main_roi'].y_min}, {summary['main_roi'].y_max}]")
print(f"  范围: Z[{summary['main_roi'].z_min}, {summary['main_roi'].z_max}]")
```

---

## 📋 常用操作

### 创建自定义ROI

```python
roi = service.create_roi(
    recipe_id=1,
    roi_name='第2层自定义ROI',
    roi_type='CUSTOM',
    layer_no=2,
    x_min=-100, x_max=100,
    y_min=-80, y_max=80,
    z_min=960, z_max=1020,
    description='用于特殊定位区域'
)

print(f"✓ 创建ROI: {roi.roi_name} (ID: {roi.id})")
```

### 更新ROI配置

```python
updated_roi = service.update_roi(
    roi_id=5,
    x_min=-150,  # 调整X范围
    x_max=150,
    description='更新后的描述'
)

print(f"✓ 已更新ROI: {updated_roi.roi_name}")
```

### 获取指定类型的ROI

```python
# 获取所有支撑面ROI
support_rois = service.get_rois_by_type(
    recipe_id=1,
    roi_type='SUPPORT_PLANE',
    enabled_only=True
)

for roi in support_rois:
    print(f"- {roi.roi_name} (层{roi.layer_no})")
```

### 获取指定层的ROI

```python
# 获取第2层的所有ROI
layer2_rois = service.get_rois_by_layer(
    recipe_id=1,
    layer_no=2,
    enabled_only=True
)

for roi in layer2_rois:
    print(f"- {roi.roi_name} ({roi.get_roi_type_display()})")
```

---

## 🌐 API调用示例

### 使用curl命令

#### 1. 批量创建层ROI
```bash
curl -X POST http://localhost:8000/vision/roi-3d/layer/batch-create/ \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_id": 1,
    "layer_no": 1
  }'
```

#### 2. 获取ROI列表
```bash
# 获取第1层的所有ROI
curl "http://localhost:8000/vision/roi-3d/list/?recipe_id=1&layer_no=1"

# 获取所有支撑面ROI
curl "http://localhost:8000/vision/roi-3d/list/?recipe_id=1&roi_type=SUPPORT_PLANE"
```

#### 3. 获取层ROI汇总
```bash
curl "http://localhost:8000/vision/roi-3d/layer/summary/?recipe_id=1&layer_no=1"
```

#### 4. 创建单个ROI
```bash
curl -X POST http://localhost:8000/vision/roi-3d/create/ \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_id": 1,
    "roi_name": "第1层自定义ROI",
    "roi_type": "CUSTOM",
    "layer_no": 1,
    "x_min": -100,
    "x_max": 100,
    "y_min": -80,
    "y_max": 80,
    "z_min": 840,
    "z_max": 920
  }'
```

#### 5. 更新ROI
```bash
curl -X PUT http://localhost:8000/vision/roi-3d/5/update/ \
  -H "Content-Type: application/json" \
  -d '{
    "description": "更新后的描述",
    "enabled": true
  }'
```

#### 6. 获取统计信息
```bash
curl "http://localhost:8000/vision/roi-3d/statistics/?recipe_id=1"
```

### 使用JavaScript（前端）

```javascript
// 批量创建层ROI
async function createLayerROIs(recipeId, layerNo) {
    const response = await fetch('/vision/roi-3d/layer/batch-create/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            recipe_id: recipeId,
            layer_no: layerNo
        })
    });
    
    const data = await response.json();
    if (data.success) {
        console.log('创建成功:', data.data);
        return data.data.rois;
    }
}

// 获取层ROI汇总
async function getLayerSummary(recipeId, layerNo) {
    const response = await fetch(
        `/vision/roi-3d/layer/summary/?recipe_id=${recipeId}&layer_no=${layerNo}`
    );
    
    const data = await response.json();
    if (data.success) {
        return data.data;
    }
}

// 使用示例
createLayerROIs(1, 1).then(rois => {
    console.log('创建了', Object.keys(rois).length, '个ROI');
});

getLayerSummary(1, 1).then(summary => {
    console.log('第', summary.layer_no, '层共有', summary.total_rois, '个ROI');
});
```

---

## 🎯 实际应用场景

### 场景1：3层料架完整配置

```python
from apps.vision.roi_3d_service import ROI3DService

service = ROI3DService()
recipe_id = 1

# 为3层料架批量创建ROI
for layer_no in range(1, 4):  # 第1层、第2层、第3层
    rois = service.batch_create_layer_rois(
        recipe_id=recipe_id,
        layer_no=layer_no
    )
    print(f"✓ 第{layer_no}层: 创建了 {len(rois)} 个ROI")

# 查看统计
stats = service.get_recipe_roi_statistics(recipe_id)
print(f"\n配方总计:")
print(f"  总ROI数: {stats['total_rois']}")
print(f"  按层分布: {stats['by_layer']}")
print(f"  按类型分布: {stats['by_type']}")
```

输出示例：
```
✓ 第1层: 创建了 4 个ROI
✓ 第2层: 创建了 4 个ROI
✓ 第3层: 创建了 4 个ROI

配方总计:
  总ROI数: 12
  按层分布: {1: 4, 2: 4, 3: 4}
  按类型分布: {'主定位ROI': 3, '支撑面ROI': 3, '前边缘ROI': 3, '立柱ROI': 3}
```

### 场景2：料架定位流程集成

```python
import numpy as np
from apps.vision.roi_3d_service import ROI3DService
from apps.vision.coordinate_transform import CoordinateTransformService

roi_service = ROI3DService()
transform_service = CoordinateTransformService()

def process_layer_positioning(recipe_id, layer_no, camera_pointcloud, robot_pose):
    """
    处理单层料架定位
    
    Args:
        recipe_id: 配方ID
        layer_no: 层号
        camera_pointcloud: 相机坐标系下的点云 (N, 3)
        robot_pose: 机器人当前位姿 (6,) [x, y, z, rx, ry, rz]
    
    Returns:
        偏移值 {'x': dx, 'y': dy, 'z': dz}
    """
    
    # 步骤1: 坐标转换（相机坐标 → 机器人坐标）
    robot_pointcloud = transform_service.transform_pointcloud(
        pointcloud=camera_pointcloud,
        T_base_flange=robot_pose,
        calibration_id=1  # 使用标定结果
    )
    
    # 步骤2: 裁剪ROI
    cropped = roi_service.crop_pointcloud_by_layer(
        pointcloud=robot_pointcloud,
        recipe_id=recipe_id,
        layer_no=layer_no
    )
    
    # 步骤3: 提取刚性基准
    support_cloud = cropped['support_plane']  # 支撑面点云
    front_cloud = cropped['front_edge']       # 前边缘点云
    pillar_cloud = cropped['pillar']          # 立柱点云
    
    # 步骤4: 计算偏移（示例）
    # 这里需要调用实际的定位算法
    offsets = {
        'x': calculate_x_offset(pillar_cloud),     # 从立柱计算X
        'y': calculate_y_offset(front_cloud),      # 从前边缘计算Y
        'z': calculate_z_offset(support_cloud),    # 从支撑面计算Z
    }
    
    return offsets

# 使用示例
offsets = process_layer_positioning(
    recipe_id=1,
    layer_no=2,
    camera_pointcloud=captured_pointcloud,
    robot_pose=[100, 200, 900, 0, 0, 0]
)

print(f"计算得到的偏移: X={offsets['x']:.3f}, Y={offsets['y']:.3f}, Z={offsets['z']:.3f}")
```

### 场景3：使用模板快速配置

```python
from apps.vision.roi_3d_service import ROI3DService

service = ROI3DService()

# 创建一个料架类型的标准模板
roi_configs = []
for layer_no in [1, 2, 3]:
    base_z = 850 + (layer_no - 1) * 120
    roi_configs.extend([
        {
            'roi_name': f'第{layer_no}层主ROI',
            'roi_type': 'MAIN',
            'layer_no': layer_no,
            'x_min': -200, 'x_max': 200,
            'y_min': -150, 'y_max': 150,
            'z_min': base_z - 20, 'z_max': base_z + 100,
            'priority': 10
        },
        # ... 其他ROI类型
    ])

# 创建模板
template = service.create_template(
    template_name='我的标准3层料架模板',
    rack_type='TYPE-A',
    layer_count=3,
    roi_configs=roi_configs
)

print(f"✓ 模板已创建: {template.template_name}")

# 应用模板到新配方
created_rois = service.apply_template(
    template_id=template.id,
    recipe_id=2,
    clear_existing=True  # 清除现有ROI
)

print(f"✓ 应用模板: 创建了 {len(created_rois)} 个ROI")
```

---

## 💡 最佳实践

### 1. ROI命名规范

建议使用清晰的命名格式：
```
格式: 第{层号}层{ROI类型}ROI

示例:
- 第1层主ROI
- 第2层支撑面ROI
- 第3层前边缘ROI
```

### 2. 坐标范围设置

**原则**：
- 主ROI覆盖整层，留有余量
- 专用ROI精确定位特征区域
- ROI之间可以重叠

**示例**：
```python
# 主ROI - 覆盖整层（宽松）
x_range = [-200, 200]  # 400mm宽
y_range = [-150, 150]  # 300mm深
z_range = [base_z-20, base_z+100]  # 120mm高

# 支撑面ROI - 靠近前边缘的水平面（紧凑）
x_range = [-180, 180]  # 360mm宽
y_range = [-130, -80]  # 50mm深（前部区域）
z_range = [base_z-10, base_z+10]  # 20mm高（薄片）
```

### 3. 优先级设置

```python
priority_map = {
    'MAIN': 10,           # 主ROI优先级最高
    'SUPPORT_PLANE': 20,  # 支撑面次之
    'FRONT_EDGE': 30,     # 前边缘
    'PILLAR': 40,         # 立柱
    'CUSTOM': 50          # 自定义最低
}
```

### 4. 错误处理

```python
try:
    rois = service.batch_create_layer_rois(
        recipe_id=recipe_id,
        layer_no=layer_no
    )
except Exception as e:
    print(f"❌ 创建ROI失败: {e}")
    # 处理错误
    
# 验证裁剪结果
cropped = service.crop_pointcloud_by_layer(...)
if cropped['support_plane'].shape[0] < 100:
    print("⚠️ 警告: 支撑面点云点数过少，可能需要调整ROI范围")
```

---

## 🔧 调试技巧

### 1. 可视化ROI范围

```python
def print_roi_info(roi):
    """打印ROI详细信息"""
    print(f"\nROI: {roi.roi_name}")
    print(f"  类型: {roi.get_roi_type_display()}")
    print(f"  层号: {roi.layer_no}")
    print(f"  范围:")
    print(f"    X: [{roi.x_min}, {roi.x_max}] (宽度: {roi.x_max - roi.x_min}mm)")
    print(f"    Y: [{roi.y_min}, {roi.y_max}] (深度: {roi.y_max - roi.y_min}mm)")
    print(f"    Z: [{roi.z_min}, {roi.z_max}] (高度: {roi.z_max - roi.z_min}mm)")
    print(f"  中心: {roi.get_center()}")
    print(f"  体积: {roi.get_volume():.0f} mm³")

# 获取ROI并打印
summary = service.get_layer_roi_summary(recipe_id=1, layer_no=1)
if summary['main_roi']:
    print_roi_info(summary['main_roi'])
```

### 2. 检查点云分布

```python
def analyze_pointcloud(pointcloud, name="点云"):
    """分析点云分布"""
    print(f"\n{name} 分析:")
    print(f"  点数: {pointcloud.shape[0]}")
    print(f"  X范围: [{pointcloud[:, 0].min():.2f}, {pointcloud[:, 0].max():.2f}]")
    print(f"  Y范围: [{pointcloud[:, 1].min():.2f}, {pointcloud[:, 1].max():.2f}]")
    print(f"  Z范围: [{pointcloud[:, 2].min():.2f}, {pointcloud[:, 2].max():.2f}]")
    print(f"  中心: [{pointcloud[:, 0].mean():.2f}, "
          f"{pointcloud[:, 1].mean():.2f}, {pointcloud[:, 2].mean():.2f}]")

# 使用
analyze_pointcloud(original_cloud, "原始点云")
analyze_pointcloud(cropped['main'], "主ROI裁剪后")
```

### 3. 对比裁剪效果

```python
def compare_roi_crops(pointcloud, recipe_id, layer_no):
    """对比不同ROI的裁剪效果"""
    cropped = service.crop_pointcloud_by_layer(
        pointcloud, recipe_id, layer_no
    )
    
    print(f"\n第{layer_no}层裁剪效果对比:")
    print(f"  原始点云: {pointcloud.shape[0]} 点")
    
    for roi_type, cloud in cropped.items():
        percentage = (cloud.shape[0] / pointcloud.shape[0]) * 100
        print(f"  {roi_type:15s}: {cloud.shape[0]:5d} 点 ({percentage:5.2f}%)")

# 使用
compare_roi_crops(my_pointcloud, recipe_id=1, layer_no=1)
```

---

## ❓ 常见问题

### Q1: 如何知道应该设置多大的ROI范围？

**A**: 
1. 先使用 `batch_create_layer_rois()` 创建默认范围
2. 采集实际点云，查看点云分布
3. 根据点云分布调整ROI范围
4. 使用 `update_roi()` 更新配置

### Q2: 点云裁剪后为空怎么办？

**A**: 
1. 检查点云坐标范围是否与ROI匹配
2. 确认坐标系是否一致（ROBOT/CAMERA）
3. 使用 `analyze_pointcloud()` 函数分析点云分布

### Q3: 如何为特殊料架创建自定义ROI？

**A**:
```python
# 使用 create_roi() 创建自定义ROI
custom_roi = service.create_roi(
    recipe_id=1,
    roi_name='特殊定位区域',
    roi_type='CUSTOM',
    layer_no=2,
    x_min=-50, x_max=50,
    y_min=-60, y_max=-40,
    z_min=960, z_max=980,
    algorithm_params={
        'custom_param': 'value'
    }
)
```

### Q4: 如何批量处理多层料架？

**A**:
```python
# 批量创建3层料架的所有ROI
for layer in range(1, 4):
    service.batch_create_layer_rois(
        recipe_id=1,
        layer_no=layer
    )
```

---

## 📚 相关文档

- [完整交付文档](./3D_ROI模块交付文档.md) - 详细的技术文档
- [手眼标定模块文档](./手眼标定模块交付文档.md) - 坐标转换模块
- [测试脚本](./test_3d_roi_module.py) - 完整的测试用例

---

**现在就开始使用3D ROI模块吧！** 🚀
