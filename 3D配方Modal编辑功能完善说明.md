# 3D配方Modal编辑功能完善说明

## 问题描述
之前3D配方的"编辑"和"新增"操作会跳转到独立页面，导致用户体验不连贯，需要在页面间跳转。用户希望像2D配方一样，在当前页面通过弹窗完成所有操作。

## 解决方案
为3D配方添加完整的Modal编辑弹窗，实现在主配方页面内完成所有3D配方的增删改查操作。

## 实现内容

### 1. 新增3D配方编辑Modal
添加了专门的3D配方编辑弹窗 `recipe-3d-modal`，包含完整的表单字段：

#### Modal结构
```html
<div id="recipe-3d-modal" class="modal-overlay">
  <div class="modal-content">
    <div class="modal-header">
      <h3 id="modal-3d-title">新增/编辑3D配方</h3>
      <button class="modal-close" onclick="close3DModal()">×</button>
    </div>
    <div class="modal-body">
      <!-- 基本信息 -->
      - 配方名称
      - 适用层号
      
      <!-- ROI参数区 -->
      - X Min/Max
      - Y Min/Max
      - Z Min/Max
      
      <!-- 标准坐标区 -->
      - 标准 X/Y/Z/Rz
    </div>
    <div class="modal-footer">
      <button onclick="close3DModal()">取消</button>
      <button onclick="submit3DModal()">保存</button>
    </div>
  </div>
</div>
```

### 2. 表单样式增强
添加了3D配方表单专用的CSS样式：

```css
/* 表单行布局 */
.form-row { 
  display: grid; 
  grid-template-columns: 1fr 1fr; 
  gap: 16px; 
}

.form-row-3 { 
  display: grid; 
  grid-template-columns: 1fr 1fr 1fr; 
  gap: 12px; 
}

/* 表单区块样式 */
.form-section {
  margin: 20px 0;
  padding: 18px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.form-section-title {
  font-size: 14px;
  font-weight: 700;
  color: #475569;
  margin: 0 0 14px;
}

.form-section-title::before {
  content: "▸";
  color: var(--primary);
}
```

### 3. JavaScript函数完善

#### 新增函数
- `create3DRecipe()` - 打开新增3D配方Modal
- `edit3DRecipe(id)` - 打开编辑3D配方Modal（从API加载数据）
- `close3DModal()` - 关闭3D配方Modal
- `submit3DModal()` - 提交3D配方表单（新增或更新）

#### 更新函数
- `openCreateModal()` - 根据当前标签页智能决定打开2D或3D Modal
- `delete3DRecipe(id, name)` - 保持原有删除功能
- `toggle3DEnabled(id, enabled)` - 保持原有启用/禁用功能

### 4. Modal交互优化

#### 打开Modal时机
- 点击3D标签页的"新增配方"按钮 → 打开3D新增Modal
- 点击3D配方卡片的"编辑"按钮 → 打开3D编辑Modal（自动填充数据）

#### 关闭Modal方式
- 点击"取消"按钮
- 点击右上角"×"按钮
- 点击Modal背景区域
- 按下ESC键

#### 表单验证
- 必填项验证：配方名称、层号
- 层号范围验证：1-10
- 失败时focus到错误字段

### 5. API调用

#### 查询配方（用于编辑）
```javascript
GET /vision/api/vision-3d-recipes/?id={id}
```

#### 新增配方
```javascript
POST /vision/api/vision-3d-recipes/
Body: {
  recipe_name, layer_no, standard_x, standard_y, standard_z, standard_rz,
  roi_config: { target_roi: { x_min, x_max, y_min, y_max, z_min, z_max } },
  enabled: true
}
```

#### 更新配方
```javascript
PATCH /vision/api/vision-3d-recipes/
Body: { id, ...同上 }
```

## 用户体验改进

### 改进前
1. 点击"编辑" → 跳转到独立页面
2. 编辑完成 → 点击保存 → 页面刷新
3. 需要手动返回主配方页面
4. 标签页状态丢失

### 改进后
1. 点击"编辑" → 在当前页面打开Modal
2. 编辑完成 → 点击保存 → Modal关闭
3. 配方列表自动刷新
4. 保持在3D配方标签页
5. 无需页面跳转，操作连贯流畅

## 功能对比

| 操作 | 2D配方 | 3D配方（现在） |
|------|--------|----------------|
| 查看列表 | ✅ 标签页 | ✅ 标签页 |
| 新增配方 | ✅ Modal | ✅ Modal |
| 编辑配方 | ✅ Modal | ✅ Modal |
| 删除配方 | ✅ 确认对话框 | ✅ 确认对话框 |
| 启用/禁用 | ✅ 直接切换 | ✅ 直接切换 |
| 页面跳转 | ❌ 无 | ❌ 无 |

## 完整操作流程

### 新增3D配方
1. 切换到"料架定位配方（3D）"标签页
2. 点击"➕ 新增配方"按钮
3. 填写配方信息（名称、层号、ROI、标准坐标）
4. 点击"保存"按钮
5. Toast提示"配方已创建"
6. Modal自动关闭，配方列表自动刷新

### 编辑3D配方
1. 在3D配方标签页找到目标配方
2. 点击配方卡片的"编辑"按钮
3. Modal打开，自动填充配方数据
4. 修改需要更新的字段
5. 点击"保存"按钮
6. Toast提示"配方已更新"
7. Modal自动关闭，配方列表自动刷新

### 删除3D配方
1. 点击配方卡片的"删除"按钮
2. 弹出确认对话框
3. 点击"确定"
4. Toast提示"配方已删除"
5. 配方列表自动刷新

## 技术亮点

### 1. 智能按钮切换
"新增配方"按钮根据当前标签页智能判断：
- 2D标签页 → 打开2D Modal
- 3D标签页 → 打开3D Modal

### 2. 数据自动填充
编辑时自动从API加载配方数据并填充到表单，支持：
- 基本信息（名称、层号）
- ROI参数（6个字段）
- 标准坐标（4个字段）
- 使用空值合并运算符（??）处理null值

### 3. 表单区块化
将复杂表单分为两个区块：
- ROI参数区（3×2网格布局）
- 标准坐标区（2×2网格布局）
清晰易读，便于填写

### 4. 错误处理
- 网络请求失败 → Toast提示
- API返回错误 → Toast提示错误信息
- 表单验证失败 → Toast提示并focus到错误字段

## 文件修改清单
- ✅ `templates/vision/recipe_management.html`
  - 添加3D配方Modal HTML
  - 添加3D配方表单样式
  - 完善3D配方JavaScript逻辑

## 测试建议
1. ✅ 切换到3D配方标签页
2. ✅ 点击"新增配方"打开Modal
3. ✅ 填写完整信息并保存
4. ✅ 点击"编辑"打开Modal，确认数据正确填充
5. ✅ 修改部分字段并保存
6. ✅ 测试ESC键关闭Modal
7. ✅ 测试点击背景关闭Modal
8. ✅ 测试表单验证（空名称、无效层号）
9. ✅ 测试启用/禁用功能
10. ✅ 测试删除功能

## 改造完成时间
2026年7月2日

## 总结
通过添加完整的3D配方编辑Modal，彻底解决了页面跳转的问题。现在2D和3D配方都在同一个页面内完成所有操作，用户体验更加连贯流畅，符合现代Web应用的设计标准。
