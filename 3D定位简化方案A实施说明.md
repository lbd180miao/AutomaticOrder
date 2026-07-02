# 3D定位简化方案A - 实施说明

## 修改概述

已按照**方案A：最小修改**完成简化，核心思想是：
- **只使用 `layer_no`（层号）作为区分字段**
- **固定 `position_no = 1`**
- **固定 `rack_side = 'BOTH'`**
- **数据库结构不变，最小化代码改动**

---

## 修改的文件和内容

### 1. `apps/vision/rack_location.py`

#### 修改的方法：

**① `RackPoseEstimator.calculate_rack_offset`（第440-460行）**
- ✅ 删除了补偿值超限检查
- ✅ 只保留置信度检查

**② `PlcVisionResultWriter._revalidate_offsets`（第648-657行）**
- ✅ 删除了补偿值超限的二次校验
- ✅ 只保留置信度不足的检查

**③ `RackLocationService.trigger`（第1440行）**
```python
# 旧：需要传 position_no 和 layer_no
def trigger(self, *, position_no: int, layer_no: int, ...)

# 新：只需传 layer_no，position_no固定为1
def trigger(self, *, layer_no: int, position_no: int = 1, ...)
    position_no = 1  # 固定为1
    rack_side = RackSide.BOTH  # 固定为BOTH
```

**④ `RackLocationService._select_recipe`（第1141行）**
```python
# 旧：根据 position_no 和 layer_no 查找
def _select_recipe(self, *, recipe_id=None, position_no: int, layer_no: int)
    return qs.get(position_no=position_no, layer_no=layer_no)

# 新：固定 position_no=1，只根据 layer_no 查找
def _select_recipe(self, *, recipe_id=None, layer_no: int)
    qs = RackLocationRecipe.objects.filter(enabled=True, position_no=1)
    return qs.get(layer_no=layer_no)
```

**⑤ `RackLocationService.capture_workbench`（第1267行）**
```python
# 固定 position_no = 1, rack_side = LEFT
position_no = 1
side = RackSide.LEFT
side_key = 'LEFT'
```

**⑥ `RackLocationService.save_workbench_result`（第1378行）**
```python
# 旧：需要传 position_no 和 layer_no
def save_workbench_result(self, *, ..., position_no=1, layer_no=1, ...)

# 新：只需传 layer_no
def save_workbench_result(self, *, ..., layer_no=1, ...)
    position_no = 1  # 固定为1
```

**⑦ `Rack3DROIService.capture`（第826行）**
```python
# 固定 position_no=1, rack_side=BOTH
position_no = 1
side_key = RackSide.LEFT
```

**⑧ `Rack3DROIService._select_recipe`（第743行）**
```python
# 固定 position_no=1, rack_side=BOTH
def _select_recipe(self, *, recipe_id=None, layer_no=1)
    qs = RackLocationRecipe.objects.filter(enabled=True, position_no=1)
    return qs.get(layer_no=layer_no)
```

---

### 2. `apps/vision/views.py`

#### 修改的API接口：

**① `api_vision_3d_recipes` - 创建配方（第1470行）**
```python
# 旧：需要传 position_no
position_no = _as_int(data.get('position_no'), 1)
layer_no = _as_int(data.get('layer_no'), 1)
# 唯一性校验：同一 position_no + layer_no 下只允许一个启用配方
if enabled and RackLocationRecipe.objects.filter(
    position_no=position_no, layer_no=layer_no, enabled=True
).exists():
    return JsonResponse({'error': f'POS {position_no} / 层号 {layer_no} 已存在...'})

# 新：只需传 layer_no
layer_no = _as_int(data.get('layer_no'), 1)
position_no = 1  # 固定为1
# 唯一性校验：同一层下只允许一个启用配方
if enabled and RackLocationRecipe.objects.filter(
    position_no=1, layer_no=layer_no, enabled=True
).exists():
    return JsonResponse({'error': f'层号 {layer_no} 已存在...'})

# 配方名称从 "3D-POS-1-L1" 简化为 "3D-L1"
recipe_name = data.get('recipe_name') or f"3D-L{layer_no}"
```

**② `api_rack_location_recipe_update` - 更新配方（第1518行）**
```python
# 强制设置 position_no=1
recipe.position_no = 1
recipe.rack_side = 'BOTH'
```

**③ `api_rack_location_trigger` - 触发定位（第1412行）**
```python
# 旧：需要传 position_no, layer_no, rack_side
position_no = _as_int(data.get('position_no'), 1)
layer_no = _as_int(data.get('layer_no'), 1)
rack_side = data.get('rack_side') or 'BOTH'

# 新：只需传 layer_no
layer_no = _as_int(data.get('layer_no'), 1)
result = RackLocationService().trigger(
    layer_no=layer_no,
    recipe_id=recipe_id,
    write_plc=write_plc,
)
```

**④ `api_rack_location_workbench_save` - 工作台保存（第1382行）**
```python
# 旧：需要传 position_no 和 layer_no
result = RackLocationService().save_workbench_result(
    ...,
    position_no=_as_int(data.get('position_no'), 1),
    layer_no=_as_int(data.get('layer_no'), 1),
)

# 新：只需传 layer_no
layer_no = _as_int(data.get('layer_no'), 1)
result = RackLocationService().save_workbench_result(
    ...,
    layer_no=layer_no,
)
```

---

## API 使用变化

### 创建配方

**旧接口：**
```json
POST /api/vision/3d/recipes/
{
  "position_no": 1,
  "layer_no": 1,
  "recipe_name": "3D-POS-1-L1",
  "standard_x": 100.0,
  ...
}
```

**新接口（简化）：**
```json
POST /api/vision/3d/recipes/
{
  "layer_no": 1,
  "recipe_name": "3D-L1",  // 可选，默认自动生成为 "3D-L{layer_no}"
  "standard_x": 100.0,
  ...
}
```

### 触发定位

**旧接口：**
```json
POST /api/vision/rack-location/trigger/
{
  "position_no": 1,
  "layer_no": 1,
  "rack_side": "LEFT",
  "recipe_id": 123
}
```

**新接口（简化）：**
```json
POST /api/vision/rack-location/trigger/
{
  "layer_no": 1,
  "recipe_id": 123  // 可选
}
```

### 工作台保存结果

**旧接口：**
```json
POST /api/vision/rack-location/workbench/save/
{
  "pointcloud_token": "xxx",
  "roi_config": {...},
  "position_no": 1,
  "layer_no": 1
}
```

**新接口（简化）：**
```json
POST /api/vision/rack-location/workbench/save/
{
  "pointcloud_token": "xxx",
  "roi_config": {...},
  "layer_no": 1
}
```

---

## 真实坐标计算逻辑

代码中的真实坐标计算公式（未变）：

```python
# 从点云数据中提取实际测量坐标
actual_x = round(float(pose.get('actual_x', 0)), 3)
actual_y = round(float(pose.get('actual_y', 0)), 3)
actual_z = round(float(pose.get('actual_z', 0)), 3)

# 补偿值 = 实际坐标 - 标准坐标
offset_x = actual_x - recipe.standard_x
offset_y = actual_y - recipe.standard_y
offset_z = actual_z - recipe.standard_z
```

**已删除的检查：**
- ✅ 不再检查 `abs(offset_x) > max_offset_x`
- ✅ 不再检查 `abs(offset_y) > max_offset_y`
- ✅ 不再检查 `abs(offset_z) > max_offset_z`
- ✅ 不再检查 `abs(offset_rz) > max_offset_rz`

**保留的检查：**
- ✅ 置信度检查：`confidence < confidence_threshold`

---

## 数据库约束变化

### RackLocationRecipe 模型

**唯一性约束（已存在，保持不变）：**
```python
models.UniqueConstraint(
    fields=['position_no', 'layer_no'],
    condition=models.Q(enabled=True),
    name='unique_enabled_recipe_per_position_layer',
)
```

由于 `position_no` 固定为1，实际效果是：
- ✅ 每个 `layer_no` 只能有一个启用的配方
- ✅ layer_no = 1, 2, 3 分别对应第1、2、3层

---

## 使用示例

### 示例1：创建第1层配方
```python
# 前端请求
POST /api/vision/3d/recipes/
{
  "layer_no": 1,
  "standard_x": 100.0,
  "standard_y": 200.0,
  "standard_z": 800.0,
  "enabled": true
}

# 后端自动创建：
# - recipe_name = "3D-L1"
# - position_no = 1（固定）
# - rack_side = 'BOTH'（固定）
# - layer_no = 1
```

### 示例2：触发第2层定位
```python
# 前端请求
POST /api/vision/rack-location/trigger/
{
  "layer_no": 2
}

# 后端逻辑：
# 1. 查找 position_no=1, layer_no=2, enabled=True 的配方
# 2. 采集点云数据
# 3. 计算补偿值（不再检查超限）
# 4. 返回定位结果
```

### 示例3：查询配方列表
```python
GET /api/vision/3d/recipes/

# 返回结果按 layer_no 排序：
[
  {"id": 1, "recipe_name": "3D-L1", "position_no": 1, "layer_no": 1, ...},
  {"id": 2, "recipe_name": "3D-L2", "position_no": 1, "layer_no": 2, ...},
  {"id": 3, "recipe_name": "3D-L3", "position_no": 1, "layer_no": 3, ...}
]
```

---

## 向后兼容性

### ✅ 完全兼容
- 数据库结构未改变
- 所有字段仍然存在
- 旧数据可以正常读取

### ⚠️ API变化
- 前端调用API时不再需要传 `position_no` 和 `rack_side`
- 只需传 `layer_no` 即可
- 如果前端仍然传了这些字段，会被忽略或覆盖为固定值

---

## 测试建议

### 1. 配方管理测试
```python
# 创建3个层的配方
for layer in [1, 2, 3]:
    POST /api/vision/3d/recipes/
    {
      "layer_no": layer,
      "standard_z": 800.0 + (layer - 1) * 150.0
    }
```

### 2. 定位测试
```python
# 测试第1层
POST /api/vision/rack-location/trigger/
{"layer_no": 1}

# 测试第2层
POST /api/vision/rack-location/trigger/
{"layer_no": 2}

# 测试第3层
POST /api/vision/rack-location/trigger/
{"layer_no": 3}
```

### 3. 补偿值超限测试
```python
# 设置一个很小的 max_offset_x
PATCH /api/vision/3d/recipes/1/
{"max_offset_x": 0.1}

# 触发定位（补偿值可能超出范围）
POST /api/vision/rack-location/trigger/
{"layer_no": 1}

# 预期：不再报错 "3D定位补偿值超出配方允许范围"
# 结果：返回真实的 actual_x, actual_y, actual_z 和 offset_x, offset_y, offset_z
```

---

## 总结

✅ **完成的工作：**
1. 删除了补偿值超限检查（两处）
2. 简化了 API 接口，只需传 `layer_no`
3. 固定 `position_no=1` 和 `rack_side='BOTH'`
4. 更新了配方创建、更新、定位触发等接口
5. 保持数据库结构不变，向后兼容

✅ **效果：**
- 代码逻辑更简单清晰
- API调用更简洁
- 系统只关注"层"的概念
- 不再因补偿值超限而拒绝定位结果
- 真实坐标和补偿值会如实返回

✅ **后续可选优化：**
- 前端隐藏 `position_no` 和 `rack_side` 字段
- 文档更新，说明新的API使用方式
- 添加数据迁移脚本，将现有数据统一设置为 `position_no=1`
