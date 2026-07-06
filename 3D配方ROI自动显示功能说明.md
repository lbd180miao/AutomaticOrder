# 3D配方ROI自动显示功能说明

## 📋 功能概述

**问题描述：** 3D相机的2D ROI框没有根据3D配方自动显示在图像上。

**解决方案：** 在采集点云后或加载数据包后，自动从配方中加载已保存的2D ROI坐标，并显示在点云图像上。

---

## ✨ 新增功能

### 1️⃣ **采集点云后自动显示ROI**

**触发时机：** 点击「📡 采集点云」按钮，点云图像加载完成后

**工作流程：**
```
用户选择配方 → 点击采集点云 → 点云图像显示
    ↓
系统自动获取配方的roi_config.target_roi
    ↓
如果存在有效的ROI坐标 → 自动绘制在图像上
    ↓
用户可以：
  ✅ 直接点击「计算偏差」（使用自动加载的ROI）
  ✅ 点击「重画ROI」手动重新绘制
```

**状态提示：**
- ✅ 成功加载：`已自动加载配方ROI (640×480)，可直接点击「计算偏差」或「重画ROI」重新绘制。`
- ⚠️ 无ROI数据：`点云已采集，请在图上拖拽绘制 ROI。`

---

### 2️⃣ **数据包加载后自动显示ROI**

**触发时机：** 在「📦 数据包管理」中点击「加载到画布」后

**工作流程：**
```
用户打开数据包管理 → 选择历史数据包 → 点击「加载到画布」
    ↓
系统加载数据包中的点云图像
    ↓
优先尝试：从数据包的roi_config.target_roi获取ROI
    ↓
如果数据包无ROI → 尝试从当前选中配方获取ROI
    ↓
自动绘制ROI并显示在图像上
```

**状态提示：**
- ✅ 数据包有ROI：`数据包已加载，ROI已显示 (640×480)，可调整后重新计算。`
- ⚠️ 数据包无ROI：`已自动加载配方ROI (640×480)，可直接点击「计算偏差」...`

---

## 🔧 技术实现

### 修改的文件

**文件路径：** `static/vision/js/rack_locator_workbench.js`

### 核心函数

#### 1. `autoLoadAndShowRecipeRoi()` - 自动加载ROI

```javascript
/**
 * 自动加载并显示当前配方的2D ROI
 * 时机：采集点云后 / 加载数据包后
 */
async function autoLoadAndShowRecipeRoi() {
    // 1. 检查前提条件（token、图像、配方ID）
    // 2. 从后端API获取配方详情
    // 3. 提取 roi_config.target_roi
    // 4. 验证ROI有效性
    // 5. 转换坐标并应用到画布
    // 6. 更新UI状态
}
```

**关键逻辑：**
- 📡 调用 `CFG.currentRecipeUrl` 获取配方数据
- 🔍 兼容多种API响应格式（`data.recipe` / `data` / `recipe`）
- ✅ 验证ROI尺寸（w > 0 && h > 0）
- 🎨 自动转换像素坐标到显示坐标
- 🖼️ 同步显示到右侧结果区

---

#### 2. 采集点云回调增强

**修改位置：** `$('btn-capture').addEventListener('click', ...)`

```javascript
// 采集成功后，图像加载完成时
image.onload = function() {
    resizeCanvas();
    // 🆕 自动加载并显示配方ROI
    autoLoadAndShowRecipeRoi();
};
```

---

#### 3. 数据包加载增强

**修改位置：** `window.rackLocatorOfflineBridge.load(payload)`

```javascript
image.onload = function() {
    resizeCanvas();
    
    // 优先使用数据包中的ROI
    const targetRoi = payload.roi_config?.target_roi;
    if (targetRoi && targetRoi.w > 0) {
        // 直接应用数据包ROI
        applyRoiToCanvas(targetRoi);
    } else {
        // 回退到配方ROI
        autoLoadAndShowRecipeRoi();
    }
};
```

---

## 🎯 使用场景

### 场景1：正常采集流程
```
1. 打开工作台
2. 选择配方（例如：POS1 · L1）
3. 点击「📡 采集点云」
4. ✅ ROI自动显示在图像上
5. 点击「🎯 计算偏差」
6. 查看结果
```

### 场景2：切换配方后采集
```
1. 选择配方A → 采集点云 → 计算偏差
2. 切换到配方B
3. 再次点击「📡 采集点云」
4. ✅ 配方B的ROI自动显示（替换配方A的ROI）
5. 点击「🎯 计算偏差」
```

### 场景3：加载历史数据包
```
1. 点击「📦 数据包管理」
2. 选择历史数据包
3. 点击「加载到画布」
4. ✅ ROI自动显示（来自数据包或当前配方）
5. 调整ROI（可选）
6. 点击「重新定位」
```

---

## 📝 浏览器调试

### 查看日志

打开浏览器控制台（F12 → Console），可以看到：

```javascript
[采集点云] 使用API端点: /vision/api/rack-location/workbench/capture/
[自动ROI] 开始尝试加载配方ROI...
[自动ROI] 正在获取配方 42 的ROI信息...
[自动ROI] ✅ 成功加载配方ROI: {x: 100, y: 150, w: 640, h: 480}
[自动ROI] ROI已应用到画布，state.roi= {x: 100, y: 150, w: 640, h: 480}
```

### 常见日志

| 日志 | 含义 | 处理建议 |
|------|------|----------|
| `[自动ROI] 无点云token，跳过` | 还未采集点云 | 正常，先采集点云 |
| `[自动ROI] 未选择配方，跳过` | 未选择配方 | 选择一个配方 |
| `[自动ROI] 配方中无保存的 target_roi` | 配方未保存ROI | 手动绘制ROI并计算偏差（会自动保存） |
| `[自动ROI] ROI尺寸无效` | ROI数据异常 | 重新绘制并保存ROI |
| `[自动ROI] ✅ 成功加载配方ROI` | 功能正常工作 | ✅ |

---

## ⚠️ 注意事项

### 1. ROI坐标系统

- **保存格式：** 原始像素坐标（naturalWidth × naturalHeight）
- **显示格式：** 缩放后的画布坐标（canvas.width × canvas.height）
- **转换公式：** `displayX = roiX * (canvas.width / naturalWidth)`

### 2. ROI保存时机

配方的ROI会在以下时机保存到数据库：

1. **计算偏差时：** 手动绘制ROI → 点击「计算偏差」→ 自动保存
2. **后端逻辑：** `api_rack_location_workbench_calculate` 视图会保存ROI到 `recipe.roi_config`

### 3. 数据优先级

加载数据包时的ROI优先级：

```
数据包中的ROI（roi_config.target_roi）
    ↓ 如果不存在
当前选中配方的ROI
    ↓ 如果还不存在
提示用户手动绘制
```

---

## 🧪 测试清单

### 基础功能测试

- [ ] ✅ 选择配方 → 采集点云 → ROI自动显示
- [ ] ✅ 切换配方 → 采集点云 → 新配方ROI显示
- [ ] ✅ 采集点云 → 手动绘制ROI → 计算偏差 → 再次采集 → ROI恢复
- [ ] ✅ 数据包管理 → 加载数据包 → ROI显示

### 边界情况测试

- [ ] ⚠️ 未选择配方时采集 → 提示手动绘制
- [ ] ⚠️ 配方无保存ROI时采集 → 提示手动绘制
- [ ] ⚠️ ROI数据异常（w=0, h=0）→ 提示手动绘制
- [ ] ✅ 加载无ROI的数据包 → 尝试从配方加载

### 用户交互测试

- [ ] ✅ 自动加载ROI后点击「重画ROI」→ 清除旧ROI，可重新绘制
- [ ] ✅ 自动加载ROI后点击「计算偏差」→ 使用自动加载的ROI
- [ ] ✅ 状态提示清晰明确

---

## 🔄 回滚方案

如果需要回退到原版本：

```bash
# 恢复备份（如果创建了备份）
copy static\vision\js\rack_locator_workbench.js.backup static\vision\js\rack_locator_workbench.js

# 或者使用Git回退
git checkout HEAD -- static/vision/js/rack_locator_workbench.js
```

---

## 📚 相关文档

- [3D配方ROI坐标自动保存和复用功能说明.md](./3D配方ROI坐标自动保存和复用功能说明.md)
- [3D料架定位工作台-单配方显示改造完成.md](./3D料架定位工作台-单配方显示改造完成.md)

---

## 📅 更新记录

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-07-06 | v1.0 | 初始版本：实现采集点云后和数据包加载后自动显示ROI |

---

**开发完成日期：** 2026年7月6日  
**开发者：** Kiro AI Assistant  
**测试状态：** ⏳ 待测试
