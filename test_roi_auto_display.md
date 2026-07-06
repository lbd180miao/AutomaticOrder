# 3D配方ROI自动显示功能测试指南

## 🎯 测试目标

验证3D相机的2D ROI框能够在以下时机自动显示：
1. ✅ 采集点云后
2. ✅ 数据包加载后

---

## 🔧 测试准备

### 1. 确保修改已生效

1. **清除浏览器缓存**
   ```
   Chrome: Ctrl + Shift + Delete → 清除缓存
   或直接：Ctrl + F5 强制刷新
   ```

2. **检查JavaScript文件**
   - 打开浏览器开发者工具（F12）
   - 进入 Sources 标签
   - 查找 `static/vision/js/rack_locator_workbench.js`
   - 搜索 `autoLoadAndShowRecipeRoi` 函数
   - ✅ 如果找到此函数，说明修改已生效

### 2. 准备测试数据

需要至少一个已保存ROI的配方：

**方法A：使用现有配方**
```sql
-- 检查哪些配方已保存ROI
SELECT 
    id, 
    recipe_name, 
    position_no, 
    layer_no,
    roi_config
FROM vision_racklocationrecipe 
WHERE roi_config::text LIKE '%target_roi%';
```

**方法B：创建新测试配方并保存ROI**
1. 进入工作台
2. 选择任意配方
3. 采集点云
4. 手动拖拽绘制ROI
5. 点击「计算偏差」（会自动保存ROI）

---

## 📋 测试用例

### 测试用例1：采集点云后自动显示ROI ⭐⭐⭐

**前置条件：** 配方已保存ROI

**测试步骤：**
```
1. 打开工作台
   URL: http://127.0.0.1:8083/vision/rack-locator-panel/

2. 选择一个已保存ROI的配方
   例如：POS1 · L1 - 测试配方

3. 打开浏览器控制台（F12 → Console）

4. 点击「📡 采集点云」按钮

5. 等待点云图像显示（2-5秒）
```

**预期结果：**

✅ **成功标志：**
- 点云图像显示
- 绿色ROI框自动绘制在图像上
- 左下角显示：`ROI  x=100  y=150  w=640  h=480`（实际数值会不同）
- 右侧结果区也显示带ROI框的图像
- 状态栏提示：`✅ 已自动加载配方ROI (640×480)，可直接点击「计算偏差」或「重画ROI」重新绘制。`

✅ **控制台日志：**
```javascript
[采集点云] 使用API端点: /vision/api/rack-location/workbench/capture/
[自动ROI] 开始尝试加载配方ROI...
[自动ROI] 正在获取配方 XX 的ROI信息...
[自动ROI] ✅ 成功加载配方ROI: {x: 100, y: 150, w: 640, h: 480}
[自动ROI] ROI已应用到画布，state.roi= {...}
```

❌ **失败标志：**
- 点云显示但没有ROI框
- 控制台显示错误日志
- 状态栏提示：`点云已采集，请在图上拖拽绘制 ROI。`

---

### 测试用例2：切换配方后ROI更新 ⭐⭐⭐

**前置条件：** 至少两个配方都已保存ROI

**测试步骤：**
```
1. 选择配方A（POS1 · L1）
2. 采集点云 → 验证配方A的ROI显示
3. 选择配方B（POS1 · L2）
4. 再次点击「采集点云」
```

**预期结果：**

✅ 第二次采集后，显示配方B的ROI（不是配方A的ROI）
✅ ROI坐标和尺寸与配方B一致

---

### 测试用例3：配方无ROI时的降级处理 ⭐⭐

**前置条件：** 创建一个全新的配方（未保存ROI）

**测试步骤：**
```
1. 创建新配方或选择一个从未使用过的配方
2. 采集点云
```

**预期结果：**

✅ 点云图像显示
✅ 没有ROI框（预期行为）
✅ 状态栏提示：`点云已采集，请在图上拖拽绘制 ROI。`
✅ 控制台显示：`[自动ROI] 配方中无保存的 target_roi`

**后续操作：**
```
3. 手动拖拽绘制ROI
4. 点击「计算偏差」
5. 再次点击「采集点云」
```

**预期结果：**
✅ 这次应该自动显示刚才绘制的ROI

---

### 测试用例4：数据包加载后自动显示ROI ⭐⭐⭐

**前置条件：** 已有历史数据包

**测试步骤：**
```
1. 先正常采集一次点云并计算偏差
2. 点击「💾 保存数据包」
3. 点击「📦 数据包管理」
4. 选择刚才保存的数据包
5. 点击「加载到画布」
6. 关闭弹窗
```

**预期结果：**

✅ 点云图像显示在左侧画布
✅ ROI框自动显示（来自数据包）
✅ 状态栏提示：`数据包已加载，ROI已显示 (640×480)，可调整后重新计算。`
✅ 右侧结果区显示计算结果（如果有）

---

### 测试用例5：重画ROI功能仍然正常 ⭐⭐

**测试步骤：**
```
1. 采集点云 → ROI自动显示
2. 点击「重画 ROI」按钮
3. 手动拖拽绘制新的ROI
4. 点击「计算偏差」
```

**预期结果：**

✅ 点击「重画 ROI」后，自动加载的ROI被清除
✅ 可以正常手动绘制新的ROI
✅ 计算偏差使用新绘制的ROI

---

### 测试用例6：自动加载的ROI可直接用于计算 ⭐⭐⭐

**测试步骤：**
```
1. 选择配方
2. 采集点云 → ROI自动显示
3. 不手动绘制，直接点击「🎯 计算偏差」
```

**预期结果：**

✅ 计算成功
✅ 使用自动加载的ROI进行计算
✅ 右侧显示偏差结果
✅ 状态栏提示：`计算完成：定位 OK，本次3D记录已自动保存。`

---

## 🐛 常见问题排查

### 问题1：ROI没有自动显示

**检查清单：**

1. ✅ 浏览器缓存是否清除？
   ```
   解决方案：Ctrl + F5 强制刷新
   ```

2. ✅ JavaScript是否有错误？
   ```
   打开 Console 标签，查看是否有红色错误信息
   ```

3. ✅ 配方是否保存了ROI？
   ```sql
   SELECT roi_config FROM vision_racklocationrecipe WHERE id = XX;
   -- 检查 roi_config.target_roi 是否存在
   ```

4. ✅ 控制台日志是什么？
   ```javascript
   // 搜索关键字：[自动ROI]
   ```

---

### 问题2：控制台报错 404

**错误示例：**
```
GET /vision/api/3d/recipes/42/ 404 (Not Found)
```

**原因：** API端点URL配置问题

**解决方案：**
检查 `rack_locator_panel.html` 模板中的 `window.rackLocatorConfig`：
```javascript
window.rackLocatorConfig = {
    currentRecipeUrl: '{% url "vision:api_vision_3d_recipe_current" %}',
    // ...其他配置
};
```

---

### 问题3：ROI坐标不准确

**现象：** ROI框显示位置偏移

**可能原因：**
1. 图像尺寸与naturalWidth/naturalHeight不匹配
2. 画布缩放比例计算错误

**调试方法：**
```javascript
// 在控制台执行
const img = document.getElementById('rl-depth-image');
console.log({
    naturalWidth: img.naturalWidth,
    naturalHeight: img.naturalHeight,
    displayWidth: img.clientWidth,
    displayHeight: img.clientHeight,
    canvasWidth: document.getElementById('rl-canvas').width,
    canvasHeight: document.getElementById('rl-canvas').height,
});
```

---

## 📊 测试记录表

| 测试用例 | 测试人 | 测试日期 | 结果 | 备注 |
|---------|--------|----------|------|------|
| 用例1：采集点云后自动显示ROI | | | ⏳ 待测试 | |
| 用例2：切换配方后ROI更新 | | | ⏳ 待测试 | |
| 用例3：配方无ROI时的降级处理 | | | ⏳ 待测试 | |
| 用例4：数据包加载后自动显示ROI | | | ⏳ 待测试 | |
| 用例5：重画ROI功能仍然正常 | | | ⏳ 待测试 | |
| 用例6：自动加载的ROI可直接用于计算 | | | ⏳ 待测试 | |

**结果标记：**
- ✅ 通过
- ❌ 失败
- ⚠️ 部分通过
- ⏳ 待测试
- 🔧 需要修复

---

## 🎬 演示视频录制建议

如果需要录制演示视频，建议包含以下场景：

1. **场景1：** 选择配方 → 采集点云 → ROI自动显示 → 直接计算偏差 ✅
2. **场景2：** 切换配方 → 采集点云 → 新配方ROI显示 ✅
3. **场景3：** 加载数据包 → ROI自动显示 → 重新定位 ✅
4. **场景4：** ROI自动显示 → 重画ROI → 手动绘制 → 计算偏差 ✅

---

## 📞 反馈问题

如果测试过程中发现问题，请记录以下信息：

1. **复现步骤**（详细的操作流程）
2. **预期结果** vs **实际结果**
3. **浏览器控制台日志**（截图或复制文本）
4. **配方信息**（ID、名称、是否有保存ROI）
5. **浏览器版本**（Chrome / Firefox / Edge）

---

**测试指南版本：** v1.0  
**创建日期：** 2026-07-06  
**预计测试时间：** 15-20分钟
