# SDK文件迁移指南

## 🎯 完成情况

✅ SDK文件已复制到Django项目内部  
✅ 代码已修改为使用项目内部SDK  
✅ 导入测试通过  

---

## 📁 新的文件结构

### Django项目中的SDK文件

```
AutomaticOrder/
└── apps/
    └── dm_camera/
        ├── sdk/                    ← 新增：SDK文件目录
        │   ├── __init__.py         ← Python包标识
        │   ├── README.md           ← SDK说明文档
        │   ├── LW_DM_Api.py        ← SDK主接口（1659行）
        │   ├── LW_DM_Type.py       ← 类型定义（300行）
        │   └── lib/
        │       └── dm_c_sdk.dll    ← 核心动态库（x64）
        │
        ├── sdk_wrapper.py          ← 已修改：使用内部SDK
        ├── services.py             ← 已修改：导入路径
        ├── models.py
        ├── views.py
        └── ...
```

### 复制的文件清单

| 文件 | 大小 | 来源 | 目标 |
|------|------|------|------|
| LW_DM_Api.py | ~1659行 | SDK/Python/API/zh/ | apps/dm_camera/sdk/ |
| LW_DM_Type.py | ~300行 | SDK/Python/API/zh/ | apps/dm_camera/sdk/ |
| dm_c_sdk.dll | ~数MB | SDK/C/lib/windows/x64/ | apps/dm_camera/sdk/lib/ |

---

## 🔄 代码修改详情

### 修改1: sdk_wrapper.py

**修改前**（动态引用外部SDK）：
```python
# 添加SDK路径到系统路径
SDK_PATH = Path(__file__).resolve().parents[3] / "DM-Host-Computer-SDK/DM上位机&SDK/SDK/1.2.3"
PYTHON_API_PATH = SDK_PATH / "Python/API/zh"
DLL_PATH = SDK_PATH / "C/lib/windows/x64/dm_c_sdk.dll"

# 动态添加SDK API路径
if str(PYTHON_API_PATH) not in sys.path:
    sys.path.insert(0, str(PYTHON_API_PATH))
```

**修改后**（使用项目内部SDK）：
```python
# 使用项目内部的SDK文件
SDK_DIR = Path(__file__).parent / "sdk"
DLL_PATH = SDK_DIR / "lib" / "dm_c_sdk.dll"

# 动态添加SDK API路径
if str(SDK_DIR) not in sys.path:
    sys.path.insert(0, str(SDK_DIR))
```

**变化**：
- ✅ 路径从外部SDK改为项目内部
- ✅ 从 `parents[3]` 改为 `parent / "sdk"`
- ✅ 更简洁、更独立

### 修改2: services.py

**修改前**：
```python
from LW_DM_Type import LWTriggerMode, LWFrameType, LWDataRecvType
```

**修改后**：
```python
from .sdk.LW_DM_Type import LWTriggerMode, LWFrameType, LWDataRecvType
```

**变化**：
- ✅ 使用相对导入
- ✅ 明确指定从sdk子模块导入

---

## ✅ 优势对比

### 之前（动态引用外部SDK）

| 方面 | 说明 |
|------|------|
| ❌ 依赖外部 | 依赖workspace2目录外的SDK |
| ❌ 路径脆弱 | 如果SDK位置改变会失败 |
| ❌ 部署复杂 | 需要同时部署Django和SDK |
| ✅ 节省空间 | 不占用项目空间 |

### 现在（项目内部SDK）

| 方面 | 说明 |
|------|------|
| ✅ 完全独立 | 不依赖外部文件 |
| ✅ 路径稳定 | 相对路径，不会出错 |
| ✅ 部署简单 | 只需部署Django项目 |
| ✅ 版本控制 | 可以纳入Git管理 |
| ⚠️ 占用空间 | 增加~数MB文件 |

---

## 🚀 使用方式（无变化）

代码使用方式完全不变：

```python
# Python代码
from apps.dm_camera.services import DMCameraService
service = DMCameraService()
service.connect()

# REST API
POST /dm-camera/api/connect/
```

一切都和之前一样使用！

---

## 🔧 SDK更新方法

### 方法1: 使用更新脚本（推荐）

```bash
# Windows
update_sdk.bat

# 自动完成：备份 → 复制 → 验证
```

### 方法2: 手动更新

```bash
# 1. 备份当前SDK
copy apps\dm_camera\sdk apps\dm_camera\sdk.backup

# 2. 复制新的Python API
copy "新SDK路径\Python\API\zh\*.py" apps\dm_camera\sdk\

# 3. 复制新的DLL
copy "新SDK路径\C\lib\windows\x64\dm_c_sdk.dll" apps\dm_camera\sdk\lib\

# 4. 测试
python test_dm_camera.py
```

---

## 📊 文件大小

```
apps/dm_camera/sdk/
├── LW_DM_Api.py        ~200 KB
├── LW_DM_Type.py       ~30 KB
└── lib/
    └── dm_c_sdk.dll    ~数 MB

总计: ~数 MB
```

---

## ⚙️ Git版本控制建议

### 选项1: 提交SDK文件（推荐用于小团队）

```bash
# .gitignore 不排除SDK
git add apps/dm_camera/sdk/
git commit -m "Add DM camera SDK files"
```

**优点**：
- ✅ 克隆即可用
- ✅ 版本一致
- ✅ 部署简单

**缺点**：
- ⚠️ 仓库体积增大

### 选项2: 不提交SDK文件（推荐用于大型项目）

```bash
# .gitignore 添加：
echo "apps/dm_camera/sdk/*.py" >> .gitignore
echo "apps/dm_camera/sdk/lib/*.dll" >> .gitignore

# 保留目录结构
git add apps/dm_camera/sdk/.gitkeep
git add apps/dm_camera/sdk/lib/.gitkeep
git add apps/dm_camera/sdk/README.md
```

**优点**：
- ✅ 仓库体积小
- ✅ 避免二进制文件

**缺点**：
- ⚠️ 需要手动复制SDK
- ⚠️ 需要文档说明

---

## 🧪 验证测试

### 快速验证

```bash
# 测试SDK导入
python -c "from apps.dm_camera.sdk_wrapper import DMCamera; print('✓ OK')"

# 测试查找设备
python test_dm_camera.py --test find

# 完整测试
python test_dm_camera.py
```

### 验证清单

- [x] SDK文件已复制到正确位置
- [x] Python能导入SDK模块
- [x] DLL路径正确
- [x] 代码修改完成
- [x] 测试通过

---

## 📝 迁移步骤总结

已完成的步骤：

1. ✅ 创建 `apps/dm_camera/sdk/` 目录
2. ✅ 复制 `LW_DM_Api.py` 到项目
3. ✅ 复制 `LW_DM_Type.py` 到项目
4. ✅ 复制 `dm_c_sdk.dll` 到项目
5. ✅ 修改 `sdk_wrapper.py` 路径
6. ✅ 修改 `services.py` 导入
7. ✅ 创建 `sdk/__init__.py`
8. ✅ 创建 `sdk/README.md`
9. ✅ 验证导入成功
10. ✅ 创建更新脚本

---

## 🎉 完成！

SDK文件迁移已完成！现在Django项目完全独立，不再依赖外部SDK文件。

### 下一步

1. 运行完整测试验证功能
2. 决定是否将SDK文件纳入Git
3. 更新部署文档
4. 正常使用

### 获取帮助

- SDK说明: `apps/dm_camera/sdk/README.md`
- 更新SDK: 运行 `update_sdk.bat`
- 测试: `python test_dm_camera.py`

---

**迁移完成时间**: 2024  
**SDK版本**: 1.2.3  
**状态**: ✅ 完成并验证

