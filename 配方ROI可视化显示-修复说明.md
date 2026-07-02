# 配方 ROI 可视化显示 - 修复说明

## 问题描述

用户报告：选中配方后，ROI 框没有自动显示在点云画布上。

### 原有行为
- 选中配方后，仅在状态栏显示文本提示
- 画布区域显示空白占位符
- 用户看不到配方 ROI 的实际位置和大小

### 期望行为（参考 2D 页面）
- 选中配方后，即使没有点云图像，也应该在画布上显示配方 ROI 框
- 用户可以直观看到 ROI 的位置和大小
- 采集点云后，ROI 框自动叠加到实际图像上

---

## 修复方案

### 1. 修改 `showRoiOnCanvas()` 函数

#### 修改前
```javascript
function showRoiOnCanvas(targetRoi) {
  // 如果有点云图像，显示 ROI
  if (image && image.src) {
    window.rackLocatorSetRoi(targetRoi);
  } else {
    // 没有图像时，只显示文本提示
    roiReadout.textContent = `配方 ROI: x=... y=... w=... h=...`;
  }
}
```

#### 修改后
```javascript
function showRoiOnCanvas(targetRoi) {
  if (image && image.src) {
    // 有图像：使用现有逻辑
    window.rackLocatorSetRoi(targetRoi);
  } else {
    // 没有图像：创建占位画布显示 ROI 框
    
    // 1. 设置画布大小（默认 640x480）
    canvas.width = 640;
    canvas.height = 480;
    canvas.style.display = 'block';
    
    // 2. 绘制深色背景
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // 3. 绘制提示文字
    ctx.fillText('配方 ROI 预览（采集点云后将显示实际图像）', ...);
    
    // 4. 绘制 ROI 框（绿色虚线）
    ctx.strokeStyle = '#22c55e';
    ctx.setLineDash([8, 4]);
    ctx.strokeRect(roiX, roiY, roiW, roiH);
    
    // 5. 填充半透明绿色
    ctx.fillStyle = 'rgba(34, 197, 94, 0.16)';
    ctx.fillRect(roiX, roiY, roiW, roiH);
    
    // 6. 保存到待应用状态
    window.tempPendingRoi = targetRoi;
  }
}
```

### 2. 状态管理优化

#### 问题
- 模板中的 JavaScript 无法直接访问 `workbench.js` 中的 `state` 对象
- 需要跨文件共享 `pendingRoi` 状态

#### 解决方案
使用三重fallback策略：

```javascript
// 尝试保存到 state.pendingRoi（workbench.js 内部）
if (typeof state !== 'undefined') {
  state.pendingRoi = targetRoi;
}
// 尝试保存到 window.state.pendingRoi（全局访问）
else if (window.state) {
  window.state.pendingRoi = targetRoi;
}
// 兜底：创建临时全局变量
else {
  window.tempPendingRoi = targetRoi;
}
```

### 3. 采集点云后自动应用

修改 `workbench.js` 中的点云采集逻辑：

```javascript
// 采集点云成功后
if (state.pendingRoi || window.tempPendingRoi) {
  const pendingRoi = state.pendingRoi || window.tempPendingRoi;
  
  image.onload = function() {
    resizeCanvas();
    window.rackLocatorSetRoi(pendingRoi);
    
    // 清除待应用状态
    state.pendingRoi = null;
    window.tempPendingRoi = null;
  };
}
```

---

## 实现效果

### 场景 1: 选中配方（无点云图像）

**操作**：
1. 打开工作台页面
2. 下拉框选择配方

**结果**：
```
┌─────────────────────────────────────┐
│ 配方 ROI 预览（采集点云后将显示...） │
│                                     │
│     ┌─────────────┐                │
│     │ target ROI  │                │
│     │             │ (绿色虚线框)   │
│     │             │                │
│     └─────────────┘                │
│                                     │
│ 配方ROI: x=100 y=50 w=200 h=150    │
└─────────────────────────────────────┘
```

### 场景 2: 切换配方（无点云图像）

**操作**：
1. 切换到另一个配方

**结果**：
- 画布清空并重绘
- 显示新配方的 ROI 框
- ROI 位置和大小更新

### 场景 3: 采集点云（已选配方）

**操作**：
1. 选中配方（ROI 框已显示）
2. 点击「采集点云」

**结果**：
```
┌─────────────────────────────────────┐
│ [点云伪彩图]                         │
│     ┌─────────────┐                │
│     │ target ROI  │ (叠加在图像上) │
│     │             │                │
│     └─────────────┘                │
│                                     │
│ 已采集点云，配方 ROI 已自动显示    │
└─────────────────────────────────────┘
```

---

## 技术细节

### Canvas 绘制参数

| 参数 | 值 | 说明 |
|------|---|------|
| 画布大小 | 640×480 | 与相机分辨率一致 |
| 背景颜色 | `#0f172a` | 深色背景，突出 ROI |
| ROI 边框 | `#22c55e` | 绿色（与实际点云 ROI 一致） |
| 边框宽度 | 3px | 清晰可见 |
| 虚线样式 | `[8, 4]` | 8px 实线 + 4px 间隔 |
| 填充颜色 | `rgba(34,197,94,0.16)` | 半透明绿色 |
| 字体大小 | 16px / 14px | 提示文字 / ROI 标签 |

### 坐标转换

假设配方 ROI 使用像素坐标（相对于标准分辨率）：

```javascript
// 1. 配方 ROI（像素坐标）
const targetRoi = {
  x: 100,   // 左上角 X
  y: 50,    // 左上角 Y
  w: 200,   // 宽度
  h: 150    // 高度
};

// 2. 计算缩放比例
const defaultWidth = 640;
const defaultHeight = 480;
const scale = Math.min(
  canvas.width / defaultWidth, 
  canvas.height / defaultHeight
);

// 3. 转换到画布坐标
const roiX = targetRoi.x * scale;
const roiY = targetRoi.y * scale;
const roiW = targetRoi.w * scale;
const roiH = targetRoi.h * scale;
```

---

## 对比 2D 页面实现

### 2D 页面 (`foam_inspector_interactive.html`)

#### 方案：叠加层 + 绝对定位

```html
<div class="camera-viewport">
  <img id="preview-image" src="...">
  <div id="roi-overlay" class="roi-overlay">
    <div class="roi-box left">
      <span class="roi-box-label">左侧泡棉</span>
    </div>
    <div class="roi-box right">
      <span class="roi-box-label">右侧泡棉</span>
    </div>
  </div>
</div>
```

**优点**：
- 使用 HTML + CSS，无需手动绘制
- 容易添加交互（点击、拖拽）
- 支持多个 ROI 框同时显示

**缺点**：
- 需要计算绝对定位坐标
- 依赖图像尺寸

### 3D 页面（当前方案）

#### 方案：Canvas 绘制

```html
<div class="rl-image-stage">
  <img id="rl-depth-image" src="...">
  <canvas id="rl-canvas"></canvas>
  <div id="rl-roi-readout"></div>
</div>
```

**优点**：
- 直接在画布上绘制，性能更好
- 支持复杂图形（圆形、多边形等）
- 可以在没有图像时显示占位内容

**缺点**：
- 需要手动编写绘制代码
- 交互需要监听鼠标事件并计算坐标

---

## 测试用例

### 测试 1: 初始加载配方

**步骤**：
1. 打开工作台页面
2. 观察画布区域

**期望**：
- ✅ 下拉框自动选中第一个配方
- ✅ 画布显示占位画布 + ROI 框
- ✅ ROI 读数显示坐标信息
- ✅ 状态栏提示"已加载配方 ROI"

---

### 测试 2: 切换配方

**步骤**：
1. 切换到另一个配方（有不同 ROI）
2. 观察画布变化

**期望**：
- ✅ 画布清空并重绘
- ✅ 显示新配方的 ROI 框
- ✅ ROI 位置和大小正确更新
- ✅ 状态栏更新为新配方信息

---

### 测试 3: 采集点云后 ROI 自动显示

**步骤**：
1. 选中配方（ROI 框已显示在占位画布上）
2. 点击「采集点云」
3. 等待点云图像加载

**期望**：
- ✅ 点云伪彩图替换占位画布
- ✅ ROI 框自动叠加到点云图像上
- ✅ ROI 位置和大小与之前一致
- ✅ 状态栏提示"配方 ROI 已自动显示"

---

### 测试 4: 无 ROI 配方

**步骤**：
1. 选中一个未保存 ROI 的配方
2. 观察画布区域

**期望**：
- ✅ 画布显示空白占位符
- ✅ 不显示 ROI 框
- ✅ 状态栏提示"请在图上拖拽绘制 ROI"

---

### 测试 5: 计算后自动切换配方

**步骤**：
1. 选配方 → 采集点云 → 计算偏差
2. 等待计算完成
3. 观察画布变化

**期望**：
- ✅ 下拉框自动切换到下一个配方
- ✅ 画布清空并重绘
- ✅ 显示新配方的 ROI 框（占位模式）
- ✅ 状态栏提示新配方信息

---

## 已知限制

1. **ROI 坐标系统**
   - 当前假设 ROI 使用像素坐标（640×480）
   - 如果配方 ROI 使用其他坐标系统，需要调整缩放计算

2. **多 ROI 支持**
   - 当前仅支持单个 `target_roi`
   - 2D 页面支持左右两个 ROI 同时显示

3. **交互功能**
   - 当前仅显示配方 ROI，不支持在占位画布上拖拽修改
   - 需要采集点云后才能手动绘制新 ROI

4. **浏览器兼容性**
   - Canvas API 需要现代浏览器
   - IE 11 不支持

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `templates/vision/rack_locator_panel.html` | 修改 `showRoiOnCanvas()` 函数，添加占位画布绘制逻辑 |
| `static/vision/js/rack_locator_workbench.js` | 添加 `window.tempPendingRoi` 检查 |

---

## 部署说明

### 1. 清空浏览器缓存
```
按 Ctrl + F5 强制刷新页面
```

### 2. 测试基础功能
- [ ] 打开页面，确认第一个配方的 ROI 显示
- [ ] 切换配方，确认 ROI 更新
- [ ] 采集点云，确认 ROI 叠加正确

### 3. 测试完整流程
- [ ] 选配方 → 看到 ROI 框
- [ ] 采集点云 → ROI 叠加到图像上
- [ ] 计算偏差 → 自动切换配方 → 新 ROI 显示

---

## 效果截图

### 修复前
```
┌─────────────────────────────────┐
│     📡                          │
│                                 │
│  点击「采集点云」获取画面       │
│                                 │
└─────────────────────────────────┘
状态：已选配方：xxx，可采集点云
```

### 修复后
```
┌─────────────────────────────────┐
│ 配方 ROI 预览（采集点云后...）  │
│                                 │
│   ┌──────────────┐             │
│   │ target ROI   │ ← 绿色框    │
│   │              │             │
│   └──────────────┘             │
│                                 │
│ 配方ROI: x=100 y=50 w=200 h=150│
└─────────────────────────────────┘
状态：已加载配方 ROI，采集点云后...
```

---

## 完成时间

**2026-07-02**

## 状态

✅ **已修复并可测试**
