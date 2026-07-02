# 3D ROI配方表单改造测试说明

## 改造内容

### 1. 前端模板修改 (rack_location_recipe_form.html)
- ✅ 移除Canvas绘制功能（不再支持2D像素坐标绘制）
- ✅ 新增6个3D坐标输入框（机器人基坐标系，单位mm）：
  - roi_x_min, roi_x_max
  - roi_y_min, roi_y_max
  - roi_z_min, roi_z_max
- ✅ 移除"允许偏差"字段组（max_offset_x/y/z, confidence_threshold）
- ✅ 简化预计算结果显示（移除OK/NG判断）

### 2. JavaScript修改 (rack_location_roi.js)
- ✅ 移除Canvas绘制相关代码
- ✅ 改为直接从表单读取3D坐标
- ✅ 更新预计算请求，传递roi_3d参数
- ✅ 简化结果渲染（移除NG判断逻辑）

### 3. 后端视图修改 (views.py)
- ✅ 更新`_save_rack_location_recipe_from_request`函数
  - 从表单读取6个3D坐标字段
  - 保存到roi_config JSON字段，格式：
    ```json
    {
      "coordinate_system": "robot",
      "x_min": 900,
      "x_max": 1300,
      "y_min": 400,
      "y_max": 850,
      "z_min": 700,
      "z_max": 880
    }
    ```
- ✅ 更新`_rack_location_recipe_form_context`函数
  - 从roi_config提取3D坐标到roi_defaults
  - 提供默认值（例如第2层的参考范围）

## 数据结构变化

### 旧格式 (2D像素坐标)
```json
{
  "target_roi": {
    "x": 250,
    "y": 180,
    "w": 140,
    "h": 90,
    "feature_type": "rack_reference"
  }
}
```

### 新格式 (3D机器人基坐标系，mm)
```json
{
  "coordinate_system": "robot",
  "x_min": 900,
  "x_max": 1300,
  "y_min": 400,
  "y_max": 850,
  "z_min": 700,
  "z_max": 880
}
```

## 测试步骤

1. **访问配方编辑页面**
   ```
   http://127.0.0.1:8082/vision/rack-location/recipes/2/edit/
   ```

2. **验证页面显示**
   - [ ] 左侧只显示深度图预览（无Canvas绘制功能）
   - [ ] 右侧ROI参数区显示6个3D坐标输入框
   - [ ] 标准坐标字段正常显示
   - [ ] 不显示"允许偏差"字段组

3. **测试保存功能**
   - [ ] 输入3D坐标值（例如：x_min=900, x_max=1300等）
   - [ ] 点击"保存配方"
   - [ ] 检查数据库roi_config字段是否正确保存

4. **测试编辑功能**
   - [ ] 打开已有配方
   - [ ] 3D坐标值正确显示在输入框中
   - [ ] 修改后保存，验证更新成功

5. **测试预计算功能**（可选）
   - [ ] 点击"预计算标准坐标"
   - [ ] 查看返回的actual_x/y/z和offset_x/y/z
   - [ ] 不应有OK/NG判断提示

## 注意事项

1. **向后兼容性**：旧配方的roi_config仍保留target_roi格式，需要手动迁移或重新配置
2. **数据库字段**：max_offset_x/y/z和confidence_threshold字段保留在模型中，但不再从表单读取
3. **坐标系说明**：所有3D坐标使用机器人基坐标系，单位为毫米(mm)

## 示例配方数据

第2层ROI配置示例：
```
ROI X Min: 900
ROI X Max: 1300
ROI Y Min: 400
ROI Y Max: 850
ROI Z Min: 700
ROI Z Max: 880
```

标准坐标（ROI中心点）：
```
standard_x: 1100
standard_y: 625
standard_z: 790
```
