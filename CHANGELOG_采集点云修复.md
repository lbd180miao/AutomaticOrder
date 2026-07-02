# 采集点云功能修复日志

## 版本：2026-07-02 修复版

### 🐛 修复的Bug

**问题：** 点击「📡 采集点云」按钮后功能无法正常工作

**影响范围：** 3D料架定位工作台 (`/vision/rack-locator/`)

**根本原因：**
- 模板中的 `captureUrl` 配置指向了错误的API端点
- JS代码优先使用 `CFG.captureUrl`，而该URL指向通用端点而非工作台专用端点
- 导致参数传递不匹配或功能不完整

### ✅ 修复内容

#### 1. 模板配置修正 (`templates/vision/rack_locator_panel.html`)

**修改：**
- ✅ 将 `captureUrl` 从 `api_vision_3d_capture` 改为 `api_rack_location_workbench_capture`
- ✅ 将 `calculateUrl` 从 `api_vision_3d_test_locate` 改为 `api_rack_location_workbench_calculate`
- ✅ 新增 `saveUrl` 指向 `api_rack_location_workbench_save`
- ✅ 重新组织配置结构，区分工作台端点和通用端点

**变更对比：**
```diff
 window.rackLocatorConfig = {
-  captureUrl: '{% url "vision:api_vision_3d_capture" %}',
+  captureUrl: '{% url "vision:api_rack_location_workbench_capture" %}',
+  calculateUrl: '{% url "vision:api_rack_location_workbench_calculate" %}',
+  saveUrl: '{% url "vision:api_rack_location_workbench_save" %}',
   ...
 };
```

#### 2. JS逻辑增强 (`static/vision/js/rack_locator_workbench.js`)

**新增功能：**
- ✅ 添加调试日志，显示实际使用的API端点
- ✅ 增加后备URL机制
- ✅ 改进错误提示

**变更内容：**

**采集点云：**
```javascript
// 修改前
const raw = await postJson(CFG.captureUrl || CFG.legacyCaptureUrl, ...);

// 修改后
const captureApiUrl = CFG.captureUrl || CFG.legacyCaptureUrl || '/vision/api/rack-location/workbench/capture/';
console.log('[采集点云] 使用API端点:', captureApiUrl);
const raw = await postJson(captureApiUrl, ...);
```

**计算偏差：**
```javascript
// 修改前
const raw = await postJson(CFG.testLocateUrl || CFG.legacyCalculateUrl, ...);

// 修改后
const calculateApiUrl = CFG.calculateUrl || CFG.legacyCalculateUrl || CFG.testLocateUrl;
console.log('[计算偏差] 使用API端点:', calculateApiUrl);
const raw = await postJson(calculateApiUrl, ...);
```

**保存结果：**
```javascript
// 修改前
const data = await postJson(CFG.legacySaveUrl || CFG.saveUrl, ...);

// 修改后
const saveApiUrl = CFG.saveUrl || CFG.legacySaveUrl;
console.log('[保存结果] 使用API端点:', saveApiUrl);
const data = await postJson(saveApiUrl, ...);
```

### 📋 测试验证

#### 自动化测试
- ✅ 运行 `test_capture_button_issue.py` - 所有检查通过
- ✅ API端点返回200状态码
- ✅ 返回数据包含必需字段

#### 手动测试清单
- [ ] 浏览器中打开工作台页面
- [ ] 按Ctrl+F5强制刷新（清除缓存）
- [ ] 选择配方
- [ ] 点击「采集点云」按钮
- [ ] Console显示正确的API端点
- [ ] Network显示200状态码
- [ ] 点云图像正确显示
- [ ] 可以绘制ROI
- [ ] 可以计算偏差
- [ ] 可以保存结果

### 📝 相关文件

**修改的文件：**
- `templates/vision/rack_locator_panel.html` - 模板配置
- `static/vision/js/rack_locator_workbench.js` - JS逻辑

**新增的文件：**
- `test_capture_button_issue.py` - 诊断脚本
- `fix_capture_button.md` - 修复方案文档
- `采集点云按钮修复完成说明.md` - 使用说明
- `verify_fix.bat` - 快速验证脚本
- `CHANGELOG_采集点云修复.md` - 本文件

**相关端点：**
- `/vision/api/rack-location/workbench/capture/` - 工作台采集点云
- `/vision/api/rack-location/workbench/calculate/` - 工作台计算偏差
- `/vision/api/rack-location/workbench/save/` - 工作台保存结果

### 🔧 技术细节

#### API端点差异

| 特性 | 旧端点 (api_vision_3d_capture) | 新端点 (api_rack_location_workbench_capture) |
|------|-------------------------------|---------------------------------------------|
| 业务逻辑 | `Rack3DLocator().capture()` | `RackLocationService().capture_workbench()` |
| 参数 | recipe_id, rack_side, layer_no | + locate_type, layer_index |
| 点云持久化 | ❌ | ✅ (保存为.npy文件) |
| 预览图生成 | 部分 | ✅ (伪彩深度图) |
| 模拟回退 | ❌ | ✅ (相机离线时自动使用模拟点云) |
| 返回数据 | 基础信息 | pointcloud_token, preview_image_url, image_width, image_height, source |

#### 为什么需要专用端点？

工作台需要特殊功能：
1. **点云持久化** - 保存为`.npy`文件，供后续计算使用
2. **预览图生成** - 渲染伪彩深度图用于ROI绘制
3. **自动回退** - 相机离线时使用模拟点云继续测试
4. **工作流支持** - 支持多步骤操作（采集→绘制→计算→保存）

### 🎯 优化建议

#### 已实现
- ✅ 统一端点配置
- ✅ 添加调试日志
- ✅ 多层后备机制

#### 未来改进
- [ ] 统一API返回格式
- [ ] 添加请求超时处理
- [ ] 增加重试机制
- [ ] 添加进度反馈

### 📚 相关文档

- [修复方案详解](./fix_capture_button.md)
- [使用说明](./采集点云按钮修复完成说明.md)
- [诊断脚本](./test_capture_button_issue.py)
- [验证脚本](./verify_fix.bat)

### 👥 贡献者

- **修复人员：** Kiro AI Assistant
- **修复日期：** 2026-07-02
- **问题报告：** 用户反馈

### 📞 支持

如遇问题：
1. 运行诊断脚本：`python test_capture_button_issue.py`
2. 运行验证脚本：`verify_fix.bat`
3. 查看浏览器Console和Network标签
4. 检查Django服务器日志

---

**最后更新：** 2026-07-02
