# CHANGELOG

本文档记录项目的所有重要修改，遵循语义化版本规范 (MAJOR.MINOR.PATCH)。

---

## [0.4.1] - 2026-01-09

### Changed
- 重新编写 README.md 文档，以 Python API 为主
- 删除 Rust CLI 使用说明，聚焦于 Python SDK 定位
- 优化文档结构：快速开始、完整 API 文档、使用场景、GigE 配置、常见问题
- 完善 API 参数说明：每个参数都包含类型、默认值、范围、注意事项
- 新增性能对比表格，展示 Camera 类与传统 API 的性能差异
- 补充 GigE 网络配置详细步骤和 USB 相机切换说明

---

## [0.4.0] - 2026-01-09

### Added
- 新增 `CameraConfig` 类，用于配置相机参数
- 支持手动设置曝光时间（微秒）和增益值（dB）
- 支持启用/禁用自动曝光和自动增益模式
- 新增 `Camera.configure()` 方法，应用参数配置到相机
- 支持混合模式：手动曝光 + 自动增益（或反之）
- 新增 `config_example.py` 示例文件，演示参数配置用法
- 在 `camera_example.py` 中新增 5 个参数配置示例（示例 7-11）

### Technical
- FFI 层新增 `get_float_value()`, `set_float_value()`, `get_enum_value()` 函数
- Rust 实现自动关闭自动模式的逻辑（设置手动值时）
- 通过 SDK 的 `MV_CC_SetFloatValue` 和 `MV_CC_SetEnumValue` 设置参数

---

## [0.3.0] - 2026-01-09

### Added
- 新增 Python `Camera` 类，大幅提升连续拍照性能（15-30 倍）
- 支持上下文管理器（`with` 语句），自动管理资源
- 新增 `Camera.open()` 方法，初始化相机（支持 IP 直连和枚举两种模式）
- 新增 `Camera.capture()` 方法，快速拍照（每张仅需 100-200ms）
- 新增 `Camera.close_camera()` 方法，手动关闭相机
- 新增 `camera_example.py` 示例文件，包含 6 个使用示例

### Fixed
- 解决 `capture_images()` 每次调用都需要 2-3 秒初始化的性能问题
- 优化连续拍照场景的时间开销（初始化一次，重复拍照）

### Performance
- 连续拍照性能从 3秒/张 降低到 0.1-0.2秒/张
- 拍摄 100 张照片从 5 分钟降低到 18 秒

---

## [0.2.0] - 2026-01-08

### Changed
- 将 `capture_images_example()` 和 `capture_images_by_ip()` 合并为单一函数 `capture_images()`
- 通过可选参数 `camera_ip` 和 `pc_ip` 自动区分枚举模式和 IP 直连模式
- 移除 `num_images` 参数，每次调用只拍摄一张照片
- 删除 `format_example.py`，将所有示例整合到 `example.py`
- 为 `example.py` 新增交互式菜单，包含 8 个示例

### Removed
- 移除多张连拍功能（需要多次拍照时，多次调用函数）

---

## [0.1.0] - 2026-01-08

### Added
- 支持 PNG、JPEG、BMP、TIFF 四种图像格式
- 新增 `ImageFormat` 枚举和 `ImageConfig` 结构体
- 新增 `format` 和 `quality` 参数到 Python API
- 支持图像质量参数验证（JPEG: 50-99, PNG: 0-9）
- Rust CLI 新增交互式图像格式选择功能
- 支持大小写不敏感的格式名称

### Changed
- 使用 SDK 原生 `save_image_to_file()` 替代手动 BMP 保存实现
- 默认图像格式从 BMP 改为 PNG（压缩质量 5）
- 文件扩展名自动根据格式生成（`.png`, `.jpg`, `.bmp`, `.tif`）

### Removed
- 删除 `save_mono8_as_bmp()` 函数（53 行代码）

### Performance
- PNG 格式下文件大小通常减少 3-10 倍

---

## 版本说明

### 版本号规则
- **MAJOR**: 重大不兼容更改（需明确指示才修改）
- **MINOR**: 新增功能、新模块（向后兼容）
- **PATCH**: Bug 修复、文档更新（向后兼容）

### 发布历史
- `0.4.1` - 文档重构
- `0.4.0` - 相机参数配置功能
- `0.3.0` - 高性能 Camera 类
- `0.2.0` - API 简化与统一
- `0.1.0` - 图像格式与质量配置
