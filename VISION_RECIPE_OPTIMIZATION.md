# 视觉配方模块优化说明

## 优化内容

### 1. 修复的问题

#### 1.1 NoReverseMatch 错误
- **问题**: `/vision/recipes/` 页面报 `NoReverseMatch` 错误
- **原因**: 模板中使用了不存在的URL名称 `'vision:hand_eye_calibration'`
- **修复**: 将URL名称改为正确的 `'vision:hand_eye_page'`

#### 1.2 3D配方标签页空白问题
- **问题**: 3D料架定位配方标签页时有时无，内容不显示
- **原因**: 
  - `#rack-recipe-list` 容器从未被填充数据
  - 缺少加载3D配方的JavaScript函数
  - 标签页切换时没有触发数据加载
- **修复**: 
  - 添加 `load3DRecipes()` 函数加载3D配方数据
  - 添加 `render3DRecipeCards()` 函数渲染配方卡片
  - 在标签页切换时触发数据加载

### 2. 新增功能

#### 2.1 3D配方管理完整功能
```javascript
// 新增的功能函数：
- load3DRecipes()              // 加载3D配方列表
- render3DRecipeCards()        // 渲染3D配方卡片
- select3DRecipeForEdit()      // 选择配方进行编辑
- save3DRecipe()               // 保存3D配方修改
- cancel3DRecipeEdit()         // 取消编辑
- disable3DRecipe()            // 禁用配方
- create3DRecipe()             // 创建新配方（跳转）
```

#### 2.2 配方互通功能
- **从配方管理页跳转到工作台**: 点击"工作台中使用"按钮，自动选择该配方
- **从工作台跳转到配方管理**: 点击"配方管理"按钮，可以查看和编辑所有配方
- **URL参数支持**: 工作台支持 `?recipe_id=123` 参数，自动选择指定配方

#### 2.3 配方选择优化
- 工作台顶部显示所有已启用的配方卡片
- 点击配方卡片即可切换当前使用的配方
- 当前选中的配方会高亮显示
- 配方信息条实时显示当前配方的关键参数

## 使用流程

### 场景1：在配方管理页面管理3D配方

1. 访问 `/vision/recipes/`
2. 点击"料架定位配方（3D）"标签页
3. 查看所有3D配方列表
4. 点击"编辑"按钮修改配方参数
5. 点击"工作台中使用"直接跳转到工作台并选中该配方

### 场景2：在工作台中使用配方

1. 访问 `/vision/rack-locator/`
2. 在顶部配方选择区域，点击想要使用的配方卡片
3. 当前选中配方信息会显示在信息条中
4. 点击"采集点云"开始使用该配方进行定位
5. 如需修改配方参数，点击"🧩 配方管理"跳转到配方管理页面

### 场景3：通过URL参数快速选择配方

直接访问：`/vision/rack-locator/?recipe_id=5`
- 工作台会自动选择ID为5的配方
- 适用于从其他系统或页面链接过来的场景

## API端点

### 3D配方相关API

```
GET  /vision/api/rack-location/recipes/           # 获取配方列表
POST /vision/api/rack-location/recipes/           # 创建新配方
POST /vision/api/rack-location/recipes/<id>/update/  # 更新配方
```

#### 获取配方列表
```bash
GET /vision/api/rack-location/recipes/?enabled=true&position_no=1&layer_no=1
```

响应：
```json
{
  "success": true,
  "recipes": [
    {
      "id": 1,
      "recipe_name": "3D-POS-1-L1",
      "position_no": 1,
      "layer_no": 1,
      "standard_x": 100.0,
      "standard_y": 200.0,
      "standard_z": 300.0,
      "standard_rz": 0.0,
      "max_offset_x": 50.0,
      "max_offset_y": 50.0,
      "max_offset_z": 30.0,
      "max_offset_rz": 5.0,
      "confidence_threshold": 0.7,
      "enabled": true
    }
  ]
}
```

#### 更新配方
```bash
POST /vision/api/rack-location/recipes/1/update/
Content-Type: application/json

{
  "recipe_name": "更新后的配方名称",
  "standard_x": 105.0,
  "standard_y": 205.0,
  "enabled": true
}
```

## 数据模型

### RackLocationRecipe 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| recipe_name | string | 配方名称 |
| rack_type | string | 料架类型 |
| rack_side | string | 料架侧（LEFT/RIGHT/BOTH） |
| position_no | int | 位置号 |
| layer_no | int | 层号 |
| layer_count | int | 总层数 |
| standard_x | float | 标准X坐标(mm) |
| standard_y | float | 标准Y坐标(mm) |
| standard_z | float | 标准Z坐标(mm) |
| standard_rz | float | 标准RZ角度(°) |
| max_offset_x | float | X轴最大偏移(mm) |
| max_offset_y | float | Y轴最大偏移(mm) |
| max_offset_z | float | Z轴最大偏移(mm) |
| max_offset_rz | float | RZ轴最大偏移(°) |
| confidence_threshold | float | 置信度阈值 |
| enabled | bool | 是否启用 |
| roi_config | json | ROI配置 |
| reference_feature_config | json | 参考特征配置 |
| hand_eye_config | json | 手眼标定配置 |

## 界面说明

### 配方管理页面（/vision/recipes/）

#### 2D泡棉配方标签页
- 显示所有2D泡棉检测配方
- 支持创建、编辑、复制、删除配方
- 可调整ROI区域和阈值参数

#### 3D料架定位配方标签页（优化后）
- 显示所有已启用的3D料架定位配方
- 每个配方显示：
  - 配方名称
  - POS和层号
  - 标准位姿（X/Y/Z/RZ）
  - 最大偏移阈值
  - 置信度阈值
- 操作按钮：
  - **编辑**: 在页面内编辑配方参数
  - **工作台中使用**: 跳转到工作台并自动选中该配方
  - **禁用**: 禁用配方（不删除）

### 3D料架定位工作台（/vision/rack-locator/）

#### 配方选择区（优化后）
- 顶部显示所有已启用的配方卡片
- 点击卡片切换当前使用的配方
- 选中的配方会高亮显示（蓝色边框）
- 底部信息条显示当前配方的关键参数
- 支持URL参数自动选择配方

#### 工作流程
1. 选择配方（点击卡片）
2. 点击"📡 采集点云"获取深度图像
3. 在图像上拖拽绘制ROI区域
4. 点击"🎯 计算偏差"进行定位计算
5. 查看计算结果（偏差值、置信度等）
6. 可选：保存结果到数据库或写入PLC

## 技术实现细节

### 1. 延迟加载优化
3D配方数据采用延迟加载策略：
- 初始页面加载时不加载3D配方数据
- 当用户首次切换到3D配方标签页时才加载
- 避免不必要的API请求，提升页面加载速度

### 2. 状态管理
```javascript
// 全局状态变量
let foam2DRecipes = [];        // 2D泡棉配方列表
let rack3DRecipes = [];        // 3D料架配方列表
let selected3DRecipeForEdit = null;  // 当前编辑的3D配方
```

### 3. URL参数解析
```javascript
// 从URL参数获取配方ID
const urlParams = new URLSearchParams(window.location.search);
const recipeIdFromUrl = urlParams.get('recipe_id');
```

### 4. 配方选择联动
```javascript
// 工作台选择配方后，自动更新：
- 隐藏输入框 recipe-id
- 手动调整区的 position-no 和 layer-no
- 信息条中的配方详情显示
- 状态提示文本
```

## 测试建议

### 功能测试

1. **配方管理页测试**
   - [ ] 切换到3D配方标签页，确认配方列表正常显示
   - [ ] 点击"编辑"按钮，确认编辑表单正确填充数据
   - [ ] 修改配方参数并保存，确认保存成功
   - [ ] 点击"工作台中使用"，确认跳转到工作台并选中对应配方
   - [ ] 点击"禁用"，确认配方被禁用且从列表中移除

2. **工作台测试**
   - [ ] 访问工作台，确认配方卡片区域显示所有配方
   - [ ] 点击不同配方卡片，确认选中状态切换正确
   - [ ] 确认信息条实时显示当前配方参数
   - [ ] 使用URL参数访问：`?recipe_id=X`，确认自动选中对应配方
   - [ ] 点击"配方管理"按钮，确认跳转到配方管理页

3. **互通性测试**
   - [ ] 在配方管理页编辑配方 → 跳转工作台 → 确认使用最新配方数据
   - [ ] 在工作台选择配方 → 跳转配方管理 → 编辑保存 → 返回工作台 → 刷新后确认数据已更新

### 浏览器兼容性测试
- [ ] Chrome
- [ ] Firefox
- [ ] Edge
- [ ] Safari（如适用）

## 后续优化建议

1. **配方版本管理**: 记录配方的修改历史，支持回滚到历史版本
2. **配方复制功能**: 在配方管理页支持复制现有配方创建新配方
3. **配方导入导出**: 支持JSON格式的配方导入导出，便于备份和迁移
4. **配方搜索过滤**: 在配方列表较多时，支持按POS、层号、名称等条件搜索
5. **批量操作**: 支持批量启用/禁用配方
6. **配方验证**: 在保存前验证配方参数的合理性（如偏移阈值不能为负数）
7. **实时预览**: 编辑配方参数时，实时显示理论位姿的3D可视化
8. **智能推荐**: 根据历史定位数据，自动推荐最优的阈值参数

## 问题排查

### 如果3D配方列表仍然不显示

1. 检查浏览器控制台是否有JavaScript错误
2. 检查网络请求，确认API返回了正确的数据
3. 检查数据库中是否有 `enabled=True` 的配方记录
4. 确认CSRF token正确传递

### 如果工作台无法选择配方

1. 检查页面是否正确渲染了配方卡片
2. 检查配方卡片的 `data-recipe-id` 属性是否正确
3. 检查JavaScript中的 `selectRecipeCard` 函数是否正确绑定
4. 确认配方数据通过Django模板正确传递到前端

## 相关文件

- `templates/vision/recipe_management.html` - 配方管理页面模板（已优化）
- `templates/vision/rack_locator_panel.html` - 料架定位工作台模板（已优化）
- `apps/vision/views.py` - 视图函数（API端点）
- `apps/vision/urls.py` - URL路由配置
- `apps/vision/models.py` - 数据模型定义

---

最后更新: 2026-07-02
