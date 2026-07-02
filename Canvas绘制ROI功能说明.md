# Canvas 绘制 ROI 功能说明

## 📋 功能概述

在 3D 配方页面添加了 Canvas 可视化绘制 ROI 功能，用户可以直接在深度伪彩图上拖拽绘制矩形框，系统自动将2D像素坐标转换为3D机器人坐标。

## 🎯 解决的问题

**之前的问题**：
- ❌ 页面显示 2D 深度图，但用户需要手动输入 3D 坐标数值
- ❌ 用户无法看到 ROI 在图像上的实际位置
- ❌ 输入 6 个坐标参数（X/Y/Z 的 min/max）繁琐且容易出错
- ❌ 用户觉得在"画2D框"，但实际需要的是3D坐标

**现在的解决方案**：
- ✅ 在深度图上拖拽鼠标直接绘制 ROI 矩形框
- ✅ 自动将2D像素坐标转换为相机坐标系3D ROI
- ✅ 自动将相机坐标转换为机器人基坐标系3D ROI
- ✅ 自动填充到表单，用户可微调
- ✅ 可视化 + 自动化，提升用户体验

## 🏗️ 技术架构

### 1. 前端层次结构

```
┌─────────────────────────────────────┐
│   深度伪彩图 (640x480)              │
│                                     │
│  ┌───────────────────────────────┐ │
│  │  Canvas 透明叠加层            │ │
│  │  - 监听鼠标拖拽                │ │
│  │  - 绘制半透明矩形框            │ │
│  │  - 显示坐标提示                │ │
│  └───────────────────────────────┘ │
└─────────────────────────────────────┘
```

### 2. 坐标转换流程

```
步骤1: 用户拖拽绘制 2D 矩形
   ↓
[x1, y1, x2, y2] (像素坐标)

步骤2: 像素坐标 → 相机坐标系 3D ROI
   ↓
使用针孔相机模型:
  X_camera = (pixel_x - cx) * Z / fx
  Y_camera = (pixel_y - cy) * Z / fy
  Z_camera = depth
   ↓
[x_min, x_max, y_min, y_max, z_min, z_max] (相机坐标, mm)

步骤3: 相机坐标 → 机器人基坐标 (调用后端API)
   ↓
POST /coordinates/api/transform-roi/
  - 使用手眼标定矩阵 (T_flange_camera)
  - 使用机器人位姿 (T_base_flange)
  - 转换所有8个顶点，重新计算AABB
   ↓
[x_min, x_max, y_min, y_max, z_min, z_max] (机器人基坐标, mm)

步骤4: 自动填充到表单
```

## 📁 文件清单

### 新增文件

1. **`static/vision/js/rack_location_canvas_roi.js`**
   - Canvas 绘制交互逻辑
   - 鼠标事件处理
   - 坐标转换算法
   - 表单自动填充

### 修改文件

2. **`templates/vision/rack_location_recipe_form.html`**
   - 添加 Canvas 覆盖层
   - 添加 ROI 提示框
   - 添加"重画 ROI"按钮
   - 引入新的 JS 文件
   - 更新页面提示文字

## 🎨 用户操作流程

### 完整流程

```
1. 点击"📡 采集标准图"
   ↓
2. 深度伪彩图加载完成
   ↓
3. 在图像上拖拽鼠标绘制矩形框
   - 实时显示框的尺寸
   - 绘制半透明绿色矩形
   ↓
4. 松开鼠标
   - 显示"🔄 正在转换坐标..."
   ↓
5. 自动坐标转换
   - 像素 → 相机坐标（前端）
   - 相机 → 机器人坐标（后端API）
   ↓
6. 自动填充到表单
   - 相机坐标 ROI（6个字段）
   - 机器人坐标 ROI（6个字段）
   ↓
7. 显示"✅ ROI 坐标已自动转换并填充"
   ↓
8. 用户可微调坐标值（可选）
   ↓
9. 点击"🎯 预计算标准坐标"验证
   ↓
10. 点击"保存配方"
```

### 辅助操作

- **重画 ROI**：点击"🔄 重画 ROI"按钮清除当前ROI，重新绘制
- **手动调整**：自动填充后可在表单中微调坐标数值

## 🔧 技术细节

### 相机内参（针孔模型）

```javascript
const CAMERA_INTRINSICS = {
  fx: 600.0,  // 焦距 X
  fy: 600.0,  // 焦距 Y
  cx: 320.0,  // 主点 X (640/2)
  cy: 240.0,  // 主点 Y (480/2)
};
```

**说明**：
- 与 `apps/vision/algorithms/image_io.py` 中的 `PINHOLE_FX/FY` 对应
- 主点会根据实际图像尺寸自动调整

### 默认深度参数

```javascript
const DEFAULT_DEPTH_Z = 810.0;        // 默认深度值（mm）
const DEFAULT_Z_THICKNESS = 20.0;     // Z轴方向的厚度（mm）
```

**说明**：
- 因为深度图是2D图像，无法精确获取每个像素的深度值
- 使用默认深度值（与 MOCK_SUPPORT_Z + z_offset 对应）
- Z轴厚度设为20mm，可覆盖料架支撑面的高度变化

### 像素到相机坐标的转换

```javascript
function pixelToCameraROI(x1, y1, x2, y2) {
  const { fx, fy, cx, cy } = CAMERA_INTRINSICS;
  const centerX = (x1 + x2) / 2;
  const centerY = (y1 + y2) / 2;
  const depthZ = DEFAULT_DEPTH_Z;

  // 中心点的相机坐标
  const camCenterX = (centerX - cx) * depthZ / fx;
  const camCenterY = (centerY - cy) * depthZ / fy;
  const camCenterZ = depthZ;

  // ROI物理尺寸
  const widthMm = widthPx * depthZ / fx;
  const heightMm = heightPx * depthZ / fy;

  return {
    x_min: camCenterX - widthMm / 2,
    x_max: camCenterX + widthMm / 2,
    y_min: camCenterY - heightMm / 2,
    y_max: camCenterY + heightMm / 2,
    z_min: camCenterZ - DEFAULT_Z_THICKNESS / 2,
    z_max: camCenterZ + DEFAULT_Z_THICKNESS / 2,
  };
}
```

### 相机到机器人坐标的转换

调用现有 API：`POST /coordinates/api/transform-roi/`

```javascript
async function transformCameraToRobot(cameraROI) {
  const response = await fetch('/coordinates/api/transform-roi/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({
      layer_no: getCurrentLayerNo(),
      camera_roi: cameraROI,
      recipe_id: recipeId,
    }),
  });

  const result = await response.json();
  return result.data.robot_roi;
}
```

**后端实现**（已有）：
- 从配方或手眼标定表读取 `T_flange_camera`
- 从配方的 `capture_pose` 读取 `T_base_flange`
- 转换 ROI 的所有8个顶点
- 重新计算轴对齐包围盒 (AABB)

## 🎨 UI/UX 设计

### Canvas 绘制样式

```css
/* Canvas 覆盖层 */
#rack-location-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  cursor: crosshair;  /* 十字光标 */
}

/* ROI 提示框（居中显示） */
.roi-hint {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  background: rgba(15, 23, 42, 0.85);
  color: #e2e8f0;
  padding: 12px 20px;
  border-radius: 8px;
  backdrop-filter: blur(4px);
  pointer-events: none;  /* 不阻挡鼠标事件 */
}
```

### ROI 矩形样式

- **绘制中**：半透明绿色填充 + 2px 绿色边框
- **绘制完成**：稍深透明填充 + 3px 粗边框 + 角点标记 + 中心点

### 状态提示

- 🎯 图像已加载，拖拽鼠标绘制 ROI 框
- ✏️ 正在绘制 ROI...
- 🔄 正在转换坐标...
- ✅ ROI 坐标已自动转换并填充
- ❌ 坐标转换失败: [错误信息]

## 📊 测试要点

### 功能测试

1. **Canvas 显示**
   - [ ] 图像加载后 Canvas 正确显示
   - [ ] Canvas 尺寸与图像一致
   - [ ] 光标显示为十字

2. **ROI 绘制**
   - [ ] 可以拖拽绘制矩形
   - [ ] 实时显示尺寸提示
   - [ ] 矩形样式正确（颜色、边框）
   - [ ] 角点和中心点显示正确

3. **坐标转换**
   - [ ] 像素坐标转相机坐标正确
   - [ ] 相机坐标转机器人坐标正确
   - [ ] 表单自动填充正确

4. **边界情况**
   - [ ] 绘制太小的ROI（<10x10）提示错误
   - [ ] 图像未加载时禁用绘制
   - [ ] API调用失败时显示错误

### 集成测试

5. **与现有功能集成**
   - [ ] "采集标准图"功能正常
   - [ ] "预计算标准坐标"功能正常
   - [ ] "保存配方"功能正常
   - [ ] 与"相机 → 机器人坐标"按钮协同工作

6. **多层测试**
   - [ ] 第1层坐标转换正确
   - [ ] 第2层坐标转换正确
   - [ ] 第3层坐标转换正确

## 🚀 未来改进方向

### 1. 真实深度数据支持

**当前**：使用默认深度值 (810mm)  
**改进**：从深度图或点云数据获取实际深度值

```javascript
// 未来改进示例
async function getDepthAtPixel(x, y) {
  // 从点云数据或深度图获取实际深度
  if (state.depthData) {
    return state.depthData[Math.round(y)][Math.round(x)];
  }
  return DEFAULT_DEPTH_Z;
}
```

### 2. ROI 可编辑

**改进**：绘制后可以拖拽调整ROI的位置和大小

- 添加控制点（8个角点 + 4条边）
- 支持拖拽移动
- 支持拖拽调整尺寸

### 3. 多ROI支持

**改进**：在同一图像上绘制多个ROI

- 支撑面 ROI
- 前边缘 ROI
- 立柱 ROI

### 4. ROI 预览回显

**改进**：读取已有配方时，在Canvas上显示ROI框

- 从机器人坐标反向投影到像素坐标
- 在Canvas上绘制已有ROI的位置

### 5. 3D 可视化

**改进**：使用 Three.js 显示3D点云和ROI

- 显示真实的3D点云
- 绘制3D包围盒
- 支持旋转、缩放视角

## 🐛 已知限制

1. **深度值**：使用默认深度值，可能与实际场景有偏差
2. **Z轴范围**：Z轴厚度固定为20mm，可能需要根据实际场景调整
3. **相机内参**：使用简化的针孔模型，未考虑畸变校正
4. **单ROI**：当前只支持单个ROI，未来需支持多ROI（支撑面+边缘+立柱）

## 📚 相关文档

- [3D配方页面简化说明](./3D配方页面简化说明.md)
- [坐标转换API测试指南](./API测试指南-ROI自动保存复用.md)
- [手眼标定问题修复总结](./手眼标定问题修复总结.md)

## 🎯 总结

通过添加 Canvas 可视化绘制功能，解决了用户在 2D 图像上手动输入 3D 坐标的痛点。用户现在可以：

1. ✅ 直观地在图像上看到 ROI 的位置
2. ✅ 快速地通过拖拽绘制 ROI
3. ✅ 自动完成复杂的坐标转换
4. ✅ 减少手动输入错误

这大大提升了用户体验和操作效率！🎉
