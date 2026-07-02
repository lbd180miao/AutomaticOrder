# 「采集点云」按钮修复方案

## 问题诊断

根据代码分析，发现了以下问题：

### 1. URL配置不匹配
**问题：** 模板中的 `captureUrl` 配置指向了旧的API端点 `api_vision_3d_capture`，而不是新的工作台专用端点 `api_rack_location_workbench_capture`。

**当前配置（rack_locator_panel.html）：**
```javascript
window.rackLocatorConfig = {
  captureUrl: '{% url "vision:api_vision_3d_capture" %}',  // ❌ 旧端点
  legacyCaptureUrl: '{% url "vision:api_rack_location_workbench_capture" %}',  // ✅ 正确端点
  // ...
};
```

**JS使用方式（rack_locator_workbench.js）：**
```javascript
const raw = await postJson(CFG.captureUrl || CFG.legacyCaptureUrl, ...);
```

由于 `CFG.captureUrl` 存在，优先使用旧端点，导致可能出现：
- 参数不匹配
- 返回数据格式不一致
- 功能不完整

### 2. API端点差异

**旧端点：** `api_vision_3d_capture` → 使用 `Rack3DLocator().capture()`
- 参数: recipe_id, rack_side, layer_no
- 用途: 通用3D采集

**新端点：** `api_rack_location_workbench_capture` → 使用 `RackLocationService().capture_workbench()`
- 参数: recipe_id, rack_side, layer_no, locate_type, layer_index
- 用途: 工作台专用，包含点云持久化、预览图生成等
- 返回: pointcloud_token, preview_image_url, image_width, image_height, source

## 修复方案

### 方案1: 修改模板配置（推荐）✅

修改 `templates/vision/rack_locator_panel.html` 中的配置：

```javascript
window.rackLocatorConfig = {
  captureUrl: '{% url "vision:api_rack_location_workbench_capture" %}',  // ✅ 使用工作台端点
  autoAlignUrl: '{% url "vision:api_vision_3d_auto_align" %}',
  testLocateUrl: '{% url "vision:api_rack_location_workbench_calculate" %}',  // ✅ 同步修改
  // ... 其他配置
};
```

### 方案2: 统一API端点

让旧端点redirect到新端点，或者让旧端点也支持工作台参数。

### 方案3: 修改JS逻辑

修改 `rack_locator_workbench.js`，优先使用 `legacyCaptureUrl`：

```javascript
const raw = await postJson(CFG.legacyCaptureUrl || CFG.captureUrl, ...);
```

## 实施步骤

1. **备份当前文件**
2. **修改模板配置** - 将 `captureUrl` 指向正确的工作台端点
3. **清除浏览器缓存** - Ctrl+F5 强制刷新
4. **测试功能**
   - 打开工作台页面
   - 打开浏览器开发者工具（F12）
   - 点击「采集点云」按钮
   - 检查Network标签中的请求URL
   - 确认返回数据格式正确

## 验证测试

```bash
# 测试新端点
python test_capture_button_issue.py

# 或手动测试
python manage.py shell
>>> from django.test import Client
>>> client = Client()
>>> response = client.post('/vision/api/rack-location/workbench/capture/', data='{}', content_type='application/json')
>>> print(response.status_code)  # 应该是200
>>> print(response.json())  # 应该包含 pointcloud_token, preview_image_url等
```

## 相关文件

- `templates/vision/rack_locator_panel.html` - 模板配置
- `static/vision/js/rack_locator_workbench.js` - JS逻辑
- `apps/vision/views.py` - 视图函数
- `apps/vision/urls.py` - URL路由

## 注意事项

1. 修改后需要**强制刷新浏览器**（Ctrl+Shift+Delete清除缓存）
2. 确保Django服务器已重启
3. 检查浏览器Console是否有JS错误
4. 如果问题持续，检查浏览器Network标签查看实际请求的URL
