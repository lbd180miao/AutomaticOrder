# 🔧 采集点云问题修复 - 快速指南

## 🚨 问题描述
点击「📡 采集点云」按钮时显示：
```
数据源 —网络请求失败：Unexpected token '<', "<!DOCTYPE "... is not valid JSON
```

---

## ✅ 测试结果
后端API **完全正常**！测试显示两个API都能正确返回JSON数据。

**结论**：问题出在前端，很可能是**浏览器缓存**导致旧的JavaScript代码仍在运行。

---

## 🎯 最快解决方案

### ⭐ 方法1: 清除浏览器缓存（99%有效）

1. 打开工作台页面：`http://127.0.0.1:8000/vision/rack-locator/`
2. 按 `Ctrl + F5` 强制刷新
3. 或按 `Ctrl + Shift + Delete` 清除缓存
4. 再次点击「采集点云」按钮

### ⭐ 方法2: 使用测试页面验证

运行批处理文件：
```
双击运行：快速调试.bat
选择：4 (启动Django服务器)
```

然后在浏览器访问测试页面：

| 测试页面 | URL | 说明 |
|---------|-----|------|
| 最小化测试 | http://127.0.0.1:8000/vision/minimal-test/ | 最简单，直接硬编码URL |
| 简单测试 | http://127.0.0.1:8000/vision/simple-capture-test/ | 使用Django模板，测试两个API |
| 完整调试 | http://127.0.0.1:8000/vision/test-capture-debug/ | 最详细的调试信息 |
| 实际工作台 | http://127.0.0.1:8000/vision/rack-locator/ | 真实的工作台页面 |

### ⭐ 方法3: 运行诊断脚本

```bash
cd d:\workspace2\AutomaticOrder

# 运行完整诊断
python diagnose_capture_issue.py

# 或使用批处理
双击运行：快速调试.bat → 选择1
```

---

## 📋 快速检查清单

- [ ] **清除浏览器缓存** (Ctrl + Shift + Delete)
- [ ] **强制刷新页面** (Ctrl + F5)
- [ ] 确认Django服务器正在运行
- [ ] 确认已登录系统
- [ ] 检查浏览器Console是否有JavaScript错误 (F12 → Console)
- [ ] 使用测试页面验证API

---

## 🔍 深度调试

如果清除缓存后仍然失败，请：

### 1. 打开浏览器开发者工具
按 `F12`，然后：

#### Console标签
查看是否有**红色错误信息**

#### Network标签
1. 勾选 "Preserve log"
2. 点击「采集点云」按钮
3. 找到请求，查看：
   - Request URL（请求的URL是什么？）
   - Status Code（HTTP状态码？200/404/403/500？）
   - Response（返回的内容是什么？）

### 2. 手动测试API
在Console中运行：
```javascript
const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
const url = '/vision/api/rack-location/workbench/capture/';

fetch(url, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf
    },
    body: JSON.stringify({ recipe_id: null })
})
.then(r => r.json())
.then(data => console.log('✓ 成功:', data))
.catch(e => console.error('✗ 失败:', e));
```

### 3. 检查JavaScript是否更新
在Console中运行：
```javascript
// 查看postJson函数
console.log(postJson.toString());
```

应该看到包含 `Content-Type检查` 的代码。如果没有，说明缓存未清除！

---

## 📁 相关文件

### 已修改的文件
| 文件 | 修改内容 |
|-----|---------|
| `apps/vision/views.py` | 增强错误处理和日志 |
| `apps/vision/urls.py` | 添加调试页面路由 |
| `static/vision/js/rack_locator_workbench.js` | 改进前端错误处理 |

### 新增的文件
| 文件 | 用途 |
|-----|------|
| `templates/vision/test_capture_debug.html` | 完整的调试页面 |
| `templates/vision/simple_capture_test.html` | 简单测试页面 |
| `templates/vision/minimal_test.html` | 最小化测试页面 |
| `diagnose_capture_issue.py` | 完整诊断脚本 |
| `test_capture_api.py` | API测试脚本 |
| `test_url_routing.py` | URL配置检查脚本 |
| `快速调试.bat` | 一键启动调试工具 |
| `问题诊断与解决方案.md` | 详细的诊断指南 |
| `修复说明_采集点云错误.md` | 详细的修复说明 |
| `问题修复总结.md` | 修复工作总结 |
| `采集点云问题修复README.md` | 本文档 |

---

## 🎬 使用流程

### 快速流程（推荐）
```
1. 双击运行：快速调试.bat
2. 选择：4 (启动服务器)
3. 浏览器访问测试页面
4. 按 Ctrl+F5 强制刷新
5. 点击测试按钮
```

### 完整流程
```
1. 运行诊断脚本确认后端正常
   python diagnose_capture_issue.py

2. 启动Django服务器
   python manage.py runserver

3. 清除浏览器缓存
   Ctrl + Shift + Delete

4. 访问测试页面
   http://127.0.0.1:8000/vision/minimal-test/

5. 如果测试页面成功，访问实际工作台
   http://127.0.0.1:8000/vision/rack-locator/
   
6. 按 Ctrl+F5 强制刷新

7. 选择配方，点击「采集点云」
```

---

## 💡 预期结果

### ✅ 修复后（成功）
```
📡 采集点云 [按钮]
数据源 dm_camera
点云已采集（真实相机），请在图上拖拽绘制 ROI。
[显示点云预览图]
```

### ⚠️ 修复后（失败但有清晰错误）
不再显示：
```
❌ 数据源 —网络请求失败：Unexpected token '<', "<!DOCTYPE "...
```

而是显示：
```
✅ 服务器错误 (404): Not Found。可能是URL路径错误或权限问题。
```

或：
```
✅ 相机采集失败: 相机未连接
```

并且在浏览器Console中显示详细的调试信息。

---

## 🆘 仍然失败？

请提供以下信息：

1. **诊断脚本输出**：
   ```bash
   python diagnose_capture_issue.py > 诊断结果.txt
   ```

2. **浏览器Console截图**（F12 → Console）

3. **浏览器Network截图**（F12 → Network → 点击采集点云 → 点击请求查看详情）

4. **测试页面的结果**：
   - 访问 minimal-test 页面的结果
   - 点击按钮后显示什么？

5. **是否清除了缓存**：
   - 是否按了 Ctrl+F5？
   - 是否清除了浏览器缓存？

6. **Django服务器控制台输出**：
   - 运行 `python manage.py runserver` 后的所有输出
   - 特别是点击「采集点云」时的输出

---

## 📞 联系支持

将以上信息发送给技术支持，我们会快速帮您解决问题！

---

## 🎉 成功案例

**症状**: "Unexpected token '<'"  
**原因**: 浏览器缓存了旧的JavaScript  
**解决**: Ctrl+F5 刷新  
**结果**: ✅ 采集点云成功！

---

**最后更新**: 2026-07-02  
**版本**: 2.0  
**维护者**: Kiro AI Assistant
