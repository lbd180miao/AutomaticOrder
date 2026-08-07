# 离线数据包管理优化说明

## 问题描述

用户在点击"离线数据包管理"时，遇到以下错误：
```
数据包文件缺失: metadata.json, pointcloud.npy, hand_eye_matrix.npy, robot_pose_matrix.npy, roi_config.json
```

## 根本原因

1. **标准数据包与原始数据包混淆**
   - 系统支持两种数据包：
     - **标准数据包**：包含 metadata.json, pointcloud.npy, hand_eye_matrix.npy, robot_pose_matrix.npy, roi_config.json 等完整文件
     - **原始数据包**：只包含 PointCloud.ply 或 pointcloud.npy 等原始点云文件
   
2. **文件检查过于严格**
   - `load_package()` 方法要求所有 5 个必需文件都存在
   - `package_detail()` 在点击任何数据包时都会调用严格的检查
   - 原始数据包无法通过检查，导致报错

3. **预览图查找不够灵活**
   - 原始数据包可能使用不同的文件名（如 Image.png）
   - 文件名大小写不一致时可能找不到预览图

## 解决方案

### 1. 改进数据包类型识别（offline_data_service.py）

**`package_detail()` 方法**
```python
def package_detail(self, package_name: str) -> Dict[str, Any]:
    """获取数据包详情，支持标准数据包和原始数据包"""
    package_dir = self._package_dir(package_name)
    
    # 检查是否为原始数据包
    is_raw = self._is_raw_package(package_dir) and not (package_dir / "metadata.json").is_file()
    
    if is_raw:
        # 原始数据包，返回简化信息
        package = self.load_raw_package(package_name)
        # ... 返回原始数据包详情
    else:
        # 标准数据包
        package = self.load_package(package_name)
        # ... 返回标准数据包详情
```

### 2. 优化错误提示（offline_data_service.py）

**`load_package()` 方法**
```python
def load_package(self, package_name: str) -> Dict[str, Any]:
    """加载标准数据包（包含所有必需文件）"""
    package_dir = self._package_dir(package_name)
    
    missing = [name for name in self.REQUIRED_FILES if not (package_dir / name).is_file()]
    if missing:
        # 如果是原始数据包，提供友好的提示
        if self._is_raw_package(package_dir):
            raise OfflineDataPackageError(
                f"这是一个原始数据包（包含 PointCloud.ply），"
                f"请使用'加载'功能直接加载，或使用 load_raw_package() 方法加载。"
            )
        else:
            raise OfflineDataPackageError(f"数据包文件缺失: {', '.join(missing)}")
```

### 3. 增强预览图查找（offline_data_service.py）

**`get_raw_preview()` 方法**
```python
def get_raw_preview(self, package_name: str) -> Path:
    """获取原始数据包的预览图路径（不区分大小写）"""
    package_dir = self._package_dir(package_name)
    
    # 先尝试精确匹配
    preview_files = ["Image.png", "preview.png", "image.png", "IMAGE.PNG", "PREVIEW.PNG"]
    for preview_file in preview_files:
        preview_path = package_dir / preview_file
        if preview_path.is_file():
            return preview_path
    
    # 如果精确匹配失败，尝试不区分大小写查找
    try:
        for file in package_dir.iterdir():
            if file.is_file() and file.suffix.lower() == '.png':
                lower_name = file.name.lower()
                if 'image' in lower_name or 'preview' in lower_name:
                    return file
    except Exception:
        pass
    
    raise OfflineDataPackageError(f"数据包中未找到预览图: {package_name}")
```

### 4. 改进列表显示（offline_data_service.py）

**`_raw_package_summary()` 方法**
- 增加点云点数统计
- 改进对 PLY 和 NPY 文件的支持
- 对于空的 position_no 和 layer_no 显示 "—" 而不是 None

### 5. 支持原始数据包的重新处理（offline_data_service.py）

**`reprocess_package()` 方法**
```python
def reprocess_package(self, package_name: str, recipe_id: int, layer_no: int, 
                     modified_roi: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """重新处理数据包，支持标准数据包和原始数据包"""
    package_dir = self._package_dir(package_name)
    
    # 检查是否为原始数据包
    is_raw = self._is_raw_package(package_dir) and not (package_dir / "metadata.json").is_file()
    
    if is_raw:
        package = self.load_raw_package(package_name)
    else:
        package = self.load_package(package_name)
    # ... 继续处理
```

### 6. 优化前端显示（offline_package_manager.js）

**改进列表和详情显示**
- 原始数据包显示 "原始数据" 标记
- position_no 和 layer_no 为空时显示 "—"
- 更清晰地区分标准数据包和原始数据包

### 7. 增强视图层错误处理（offline_data_views.py）

**所有视图方法**
- 添加详细的异常捕获和日志输出
- 区分 OfflineDataPackageError 和其他异常
- 提供更友好的错误信息

## 主要改进

### ✅ 1. 数据包类型智能识别
- 自动识别标准数据包和原始数据包
- 根据数据包类型选择合适的加载方法

### ✅ 2. 友好的错误提示
- 当检测到原始数据包时，提供清晰的使用指引
- 不再显示令人困惑的"文件缺失"错误

### ✅ 3. 灵活的文件查找
- 支持多种预览图文件名（Image.png, preview.png 等）
- 不区分大小写查找

### ✅ 4. 完整的点云信息
- 显示原始数据包的点云点数
- 支持 PLY 和 NPY 格式的点云统计

### ✅ 5. 更好的用户界面
- 清晰标记原始数据包
- 空值显示为 "—" 而不是 null

### ✅ 6. 增强的日志和调试
- 详细的异常堆栈输出
- 便于问题排查和诊断

## 使用指南

### 标准数据包
- 从工作台"保存数据包"按钮创建
- 包含完整的配方、ROI、手眼标定等信息
- 可以直接重新定位

### 原始数据包
- 直接放置到 `docs/pic` 文件夹
- 只需包含 `PointCloud.ply` 或 `pointcloud.npy`
- 可选包含 `Image.png` 作为预览图
- 点击"加载"按钮导入到工作台

## 测试建议

1. **测试标准数据包**
   - 创建新数据包
   - 查看详情
   - 加载到工作台
   - 重新定位
   - 删除数据包

2. **测试原始数据包**
   - 将 PointCloud.ply 放入文件夹
   - 刷新列表，应显示为"原始数据"
   - 点击查看详情（不应报错）
   - 加载到工作台（应成功）
   - 删除数据包（应成功）

3. **测试边界情况**
   - 空文件夹
   - 缺少预览图
   - 文件名大小写不一致
   - 损坏的点云文件

## 后续优化建议

1. **数据包转换功能**
   - 提供将原始数据包转换为标准数据包的功能
   - 允许用户为原始数据包添加配方信息

2. **批量导入**
   - 支持批量导入多个原始数据包
   - 自动生成预览图

3. **数据包验证**
   - 在列表中显示数据包健康状态
   - 提供修复损坏数据包的工具

4. **搜索和过滤**
   - 按配方、时间、类型过滤数据包
   - 搜索特定的数据包

## 修改文件列表

- ✅ `apps/vision/offline_data_service.py` - 核心服务层
- ✅ `apps/vision/offline_data_views.py` - 视图层
- ✅ `static/vision/js/offline_package_manager.js` - 前端交互
- ✅ `docs/OFFLINE_PACKAGE_FIX.md` - 本文档

## 版本信息

- **修复日期**: 2026-08-06
- **影响范围**: 离线数据包管理功能
- **兼容性**: 向后兼容，不影响现有数据包
