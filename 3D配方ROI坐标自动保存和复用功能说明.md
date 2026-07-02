# 3D配方ROI坐标自动保存和复用功能说明

## 问题描述

原有的3D配方模块在使用时存在以下问题：
1. 每次调用配方时都需要重新绘制ROI框
2. 第一次绘制的ROI坐标没有被保存
3. 无法复用上次的ROI坐标，增加了操作复杂度

## 解决方案

### 核心优化

实现了ROI坐标的**自动保存**和**自动加载**功能：

1. **首次绘制ROI时**：自动保存ROI坐标到配方的`roi_config`字段
2. **再次调用配方时**：如果没有重新绘制ROI，自动加载上次保存的坐标
3. **坐标系统一**：所有保存的坐标都是**机器人基坐标系**的坐标，确保复用准确

### 实现细节

#### 1. 保存ROI坐标 (api_rack_location_workbench_save)

**位置**：`apps/vision/views.py` 第1470行左右

**功能**：
- 当用户点击"保存结果"按钮时，自动将当前绘制的ROI坐标保存到配方中
- 保存的坐标已经过坐标转换，为机器人基坐标系的坐标
- 同时记录ROI最后更新时间，方便追踪

**代码改动**：
```python
# 优化：将工作台上的 roi_config 保存回配方中，实现ROI坐标的持久化
if recipe_id and roi_config:
    recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first()
    if recipe and 'target_roi' in roi_config:
        current_config = recipe.roi_config or {}
        target_roi = roi_config['target_roi']
        
        # 保存ROI坐标（这些坐标已经是机器人基坐标系）
        current_config['target_roi'] = target_roi
        
        # 同时保存一个时间戳，方便追踪最后更新时间
        from django.utils import timezone
        current_config['target_roi_updated_at'] = timezone.now().isoformat()
        
        recipe.roi_config = current_config
        recipe.save(update_fields=['roi_config'])
        logger.info(f"已保存配方 {recipe_id} 的ROI坐标: {target_roi}")
```

#### 2. 自动加载ROI坐标 (api_rack_location_workbench_calculate)

**位置**：`apps/vision/views.py` 第1440行左右

**功能**：
- 当用户点击"计算偏差"按钮时，自动检查配方中是否有已保存的ROI
- 如果前端没有传入ROI配置，自动从配方中加载已保存的ROI
- 实现无需重新绘制，直接使用上次的坐标

**代码改动**：
```python
# 优化：如果前端没有传入ROI配置，尝试从配方中加载已保存的ROI
if recipe_id and not roi_config.get('target_roi'):
    recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first()
    if recipe and recipe.roi_config:
        saved_target_roi = recipe.roi_config.get('target_roi')
        if saved_target_roi:
            roi_config['target_roi'] = saved_target_roi
            logger.info(f"自动加载配方 {recipe_id} 的已保存ROI坐标")
```

#### 3. 新增API接口：获取配方ROI详情

**位置**：`apps/vision/views.py` 新增函数 `api_rack_location_recipe_detail`

**URL**：`GET /api/rack-location/recipes/<recipe_id>/`

**功能**：
- 获取配方的详细信息，包括已保存的ROI坐标
- 提供ROI状态信息，方便前端判断是否需要重新绘制

**返回数据结构**：
```json
{
  "success": true,
  "recipe": {
    "id": 1,
    "recipe_name": "3D-L1",
    "layer_no": 1,
    "roi_config": {
      "coordinate_system": "robot",
      "target_roi": {
        "x": 100,
        "y": 200,
        "w": 300,
        "h": 400
      },
      "target_roi_updated_at": "2026-07-02T10:30:00.000Z"
    },
    "roi_info": {
      "has_saved_roi": true,
      "target_roi": {
        "x": 100,
        "y": 200,
        "w": 300,
        "h": 400
      },
      "roi_updated_at": "2026-07-02T10:30:00.000Z"
    },
    "standard_x": 1100.0,
    "standard_y": 600.0,
    "standard_z": 850.0,
    "...": "其他配方字段"
  }
}
```

## 使用流程

### 场景1：首次使用配方

1. 选择配方（如：第1层配方）
2. 点击"采集点云"按钮
3. 在预览图上**绘制ROI框**
4. 点击"计算偏差"按钮
5. 点击"保存结果"按钮 → **ROI坐标自动保存到配方**

### 场景2：再次使用同一配方

1. 选择配方（如：第1层配方）
2. 点击"采集点云"按钮
3. **无需重新绘制ROI**，直接点击"计算偏差"按钮
4. 系统自动加载上次保存的ROI坐标进行计算
5. 如果需要调整ROI，可以重新绘制，保存后会覆盖旧的坐标

## 技术细节

### 数据存储结构

ROI坐标存储在 `RackLocationRecipe` 模型的 `roi_config` 字段（JSONField）中：

```python
{
    "coordinate_system": "robot",  # 坐标系标识
    "target_roi": {               # ROI区域
        "x": 100,                  # X坐标（像素或毫米，取决于上下文）
        "y": 200,                  # Y坐标
        "w": 300,                  # 宽度
        "h": 400                   # 高度
    },
    "target_roi_updated_at": "2026-07-02T10:30:00.000Z"  # 更新时间
}
```

### 坐标系说明

**重要**：保存的ROI坐标是**机器人基坐标系**的坐标。

坐标转换流程：
1. 用户在前端绘制的是**像素坐标**（图像坐标系）
2. 后端通过点云数据和ROI区域，提取ROI内的3D点云
3. 如果点云是**相机坐标系**，通过手眼标定矩阵转换为**机器人坐标系**
4. 计算ROI内点云的中位数，得到**机器人坐标系**的坐标
5. 这个机器人坐标系的坐标被保存到配方中

复用时：
1. 加载已保存的ROI坐标（机器人坐标系）
2. 直接使用该坐标进行定位计算
3. 无需重新进行坐标转换

## 修改的文件清单

### 1. apps/vision/views.py
- 修改 `api_rack_location_workbench_calculate` 函数：添加ROI自动加载逻辑
- 修改 `api_rack_location_workbench_save` 函数：添加ROI自动保存逻辑
- 新增 `api_rack_location_recipe_detail` 函数：提供配方ROI详情查询接口

### 2. apps/vision/urls.py
- 新增URL路由：`path('api/rack-location/recipes/<int:recipe_id>/', ...)`

### 3. 本说明文档
- 新增 `3D配方ROI坐标自动保存和复用功能说明.md`

## 前端集成建议

### 1. 加载配方时检查ROI状态

```javascript
// 获取配方详情
const response = await fetch(`/api/rack-location/recipes/${recipeId}/`);
const data = await response.json();

if (data.success && data.recipe.roi_info.has_saved_roi) {
    // 有已保存的ROI
    console.log('检测到已保存的ROI:', data.recipe.roi_info.target_roi);
    
    // 可以在UI上显示提示："此配方已有保存的ROI，可直接计算"
    showToast('此配方已有保存的ROI，可直接点击计算按钮');
    
    // 可选：自动在预览图上绘制已保存的ROI框（虚线显示）
    drawSavedROI(data.recipe.roi_info.target_roi);
} else {
    // 没有保存的ROI
    showToast('请先绘制ROI区域');
}
```

### 2. 计算时的处理逻辑

```javascript
// 点击"计算偏差"按钮
async function handleCalculate() {
    const requestData = {
        pointcloud_token: currentToken,
        recipe_id: currentRecipeId,
        layer_no: currentLayerNo,
        roi_config: {
            // 如果用户重新绘制了ROI，使用新的ROI
            // 如果没有重新绘制，不传roi_config或传空对象
            // 后端会自动加载已保存的ROI
            target_roi: newlyDrawnROI || undefined
        }
    };
    
    const response = await fetch('/api/rack-location/workbench/calculate/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(requestData)
    });
    
    const result = await response.json();
    // 处理计算结果...
}
```

### 3. 保存结果时的提示

```javascript
// 点击"保存结果"按钮后
async function handleSave() {
    const response = await fetch('/api/rack-location/workbench/save/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            pointcloud_token: currentToken,
            recipe_id: currentRecipeId,
            layer_no: currentLayerNo,
            roi_config: {
                target_roi: currentROI
            }
        })
    });
    
    const result = await response.json();
    
    if (result.success) {
        showToast('保存成功！ROI坐标已自动保存到配方，下次可直接使用');
    }
}
```

## 优势总结

### 1. 提高操作效率
- 无需每次都重新绘制ROI，节省操作时间
- 复用已验证的ROI坐标，减少人为误差

### 2. 保证数据一致性
- 统一使用机器人基坐标系，确保坐标复用准确
- 自动保存时间戳，方便追踪ROI更新历史

### 3. 降低操作复杂度
- 系统自动处理ROI的保存和加载
- 前端无需关心复杂的坐标转换逻辑

### 4. 灵活性
- 如果需要调整ROI，随时可以重新绘制
- 重新保存后会覆盖旧的坐标，保持最新状态

## 注意事项

1. **坐标系一致性**：所有保存的ROI坐标都是机器人基坐标系，请勿手动修改坐标系字段
2. **配方更新**：如果料架的物理位置发生变化，请重新绘制并保存ROI
3. **数据备份**：ROI坐标存储在数据库的JSON字段中，建议定期备份数据库
4. **兼容性**：旧的配方如果没有保存ROI，首次使用时仍需绘制ROI

## 后续优化建议

1. **批量初始化**：为所有层级的配方批量生成默认ROI
2. **ROI模板**：支持从一个配方复制ROI到其他配方
3. **历史记录**：记录ROI的修改历史，支持回滚到之前的版本
4. **可视化对比**：在UI上对比当前点云与历史ROI的偏差
5. **智能推荐**：基于点云特征自动推荐最佳ROI区域

## 测试建议

### 测试场景1：首次保存ROI
1. 创建一个新配方
2. 采集点云并绘制ROI
3. 保存结果
4. 验证数据库中配方的`roi_config`字段是否正确保存了ROI坐标

### 测试场景2：自动加载ROI
1. 使用已有ROI的配方
2. 采集点云（不绘制ROI）
3. 直接点击计算
4. 验证是否能正确使用已保存的ROI进行计算

### 测试场景3：更新ROI
1. 使用已有ROI的配方
2. 采集点云并重新绘制ROI
3. 保存结果
4. 验证数据库中的ROI坐标是否更新为新的坐标

### 测试场景4：多配方测试
1. 为第1、2、3层分别创建配方并保存ROI
2. 轮流切换配方并计算
3. 验证每个配方是否加载了正确的ROI坐标

## 日志记录

系统在以下操作时会记录日志：
- 保存ROI坐标：`已保存配方 {recipe_id} 的ROI坐标: {target_roi}`
- 加载ROI坐标：`自动加载配方 {recipe_id} 的已保存ROI坐标`

可通过查看日志文件确认ROI的保存和加载是否正常。

---

**创建时间**：2026-07-02  
**版本**：v1.0  
**作者**：Kiro AI Assistant
