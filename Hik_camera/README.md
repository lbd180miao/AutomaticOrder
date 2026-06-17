# 海康威视工业相机 Python SDK

基于 PyO3 和 Maturin 构建的海康威视工业相机 Python 绑定库，支持 GigE、USB 3.0、CameraLink 等多种接口的工业相机。

## 特性

- ✅ **高性能采集**：初始化一次，连续拍摄每张仅需 100-200ms
- ✅ **多相机支持**：支持多相机枚举和同时采集
- ✅ **IP 直连模式**：跳过枚举，直接通过 IP 连接相机
- ✅ **多格式支持**：PNG、JPEG、BMP、TIFF 格式可选
- ✅ **参数配置**：曝光时间、增益、自动模式等完整控制
- ✅ **上下文管理**：支持 `with` 语句自动资源管理

## 安装

### 前置要求

1. **安装海康威视 MVS SDK**
   - Windows: 下载并安装 [MVS SDK](https://www.hikrobotics.com/cn/machinevision/service/download)
   - 默认路径: `C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64`
   - Linux: 安装到 `/opt/MVS/lib/64/`

2. **配置 Env.json**

在项目根目录创建 `Env.json`：

**Windows:**
```json
{
  "envs": [
    {
      "key": "HCMVS_LIB",
      "value": "C:/Program Files (x86)/Common Files/MVS/Runtime/Win64_x64"
    }
  ]
}
```

**Linux:**
```json
{
  "envs": [
    {
      "key": "HCMVS_LIB",
      "value": "/opt/MVS/lib/64"
    }
  ]
}
```

### 构建安装

```bash
# 安装 maturin
pip install maturin

# 开发模式（推荐）
maturin develop --release

# 或构建 wheel 包
maturin build --release
pip install target/wheels/chg_hik-*.whl
```

## 快速开始

### 最简示例 - IP 直连

```python
import chg_hik

# 创建并打开相机
with chg_hik.Camera(output_dir="images") as cam:
    cam.open(camera_ip="192.168.1.64", pc_ip="192.168.1.100")

    # 快速拍照（每张只需 100-200ms）
    for i in range(10):
        img_path = cam.capture()
        print(f"已保存: {img_path}")
```

### 自动枚举模式

```python
import chg_hik

# 自动枚举第一个相机
with chg_hik.Camera(output_dir="images") as cam:
    cam.open()  # 不传 IP 则自动枚举

    img_path = cam.capture()
    print(f"已保存: {img_path}")
```

## API 文档

### Camera 类（推荐）

高性能相机类，适合连续采集。初始化一次，可重复拍摄。

#### 构造函数

```python
Camera(
    output_dir: str,
    camera_ip: Optional[str] = None,
    pc_ip: Optional[str] = None,
    format: str = "PNG",
    quality: int = 5
)
```

**参数：**
- `output_dir` (str): 图片输出目录路径（必需）
- `camera_ip` (Optional[str]): 相机 IP 地址（可选）
- `pc_ip` (Optional[str]): PC 网卡 IP 地址（可选）
- `format` (str): 图像格式，可选值：
  - `"PNG"` - 无损压缩（默认，推荐）
  - `"JPEG"` - 有损压缩
  - `"BMP"` - 无压缩
  - `"TIFF"` - 无损格式
- `quality` (int): 图像质量
  - PNG: 0-9（0=最快，9=最小文件，默认 5）
  - JPEG: 50-99（值越高质量越好，默认 90）
  - BMP/TIFF: 忽略此参数

#### 方法

##### open()

```python
cam.open(camera_ip: Optional[str] = None, pc_ip: Optional[str] = None)
```

打开并初始化相机。

**参数：**
- `camera_ip` (Optional[str]): 相机 IP 地址
- `pc_ip` (Optional[str]): PC 网卡 IP 地址

**模式：**
- **IP 直连模式**：同时提供 `camera_ip` 和 `pc_ip`（快速，生产推荐）
- **枚举模式**：不提供参数，自动发现第一个相机

**返回：** None

**异常：**
- `RuntimeError`: 相机已打开或初始化失败
- `ValueError`: IP 参数不完整

##### capture()

```python
img_path = cam.capture() -> str
```

快速拍照，每次仅需 100-200ms。

**返回：** str - 图片保存路径

**异常：**
- `RuntimeError`: 相机未打开或拍照失败

##### configure()

```python
cam.configure(config: CameraConfig)
```

应用相机参数配置。

**参数：**
- `config` (CameraConfig): 相机配置对象

**返回：** None

**异常：**
- `RuntimeError`: 相机未打开或配置失败

##### close_camera()

```python
cam.close_camera()
```

关闭相机并释放资源。

**返回：** None

#### 上下文管理器

支持 `with` 语句，自动管理资源：

```python
with chg_hik.Camera(output_dir="images") as cam:
    cam.open(camera_ip="192.168.1.64", pc_ip="192.168.1.100")
    cam.capture()
    # 自动调用 close_camera()
```

---

### CameraConfig 类

相机参数配置类，用于设置曝光、增益等参数。

#### 构造函数

```python
config = CameraConfig()
```

创建空配置对象，所有参数默认为 `None`（不设置）。

#### 属性

所有属性均为 `Optional` 类型，设置为 `None` 表示不修改该参数。

##### exposure_time

```python
config.exposure_time: Optional[float]
```

曝光时间，单位：微秒（μs）。

**典型范围：** 30 - 1000000
- 短曝光（1000-3000μs）：适合快速运动物体
- 中等曝光（5000-8000μs）：常规场景
- 长曝光（10000+μs）：暗环境

**注意：** 设置手动曝光时间会自动关闭自动曝光模式。

##### gain

```python
config.gain: Optional[float]
```

增益值，单位：分贝（dB）。

**典型范围：** 0 - 36
- 低增益（0-10dB）：亮环境，低噪声
- 中等增益（10-20dB）：常规场景
- 高增益（20+dB）：暗环境，可能有噪声

**注意：** 设置手动增益会自动关闭自动增益模式。

##### exposure_auto

```python
config.exposure_auto: Optional[bool]
```

自动曝光模式开关。

- `True` - 启用自动曝光（CONTINUOUS）
- `False` - 关闭自动曝光
- `None` - 不修改（默认）

##### gain_auto

```python
config.gain_auto: Optional[bool]
```

自动增益模式开关。

- `True` - 启用自动增益（CONTINUOUS）
- `False` - 关闭自动增益
- `None` - 不修改（默认）

#### 使用示例

**手动设置曝光和增益：**
```python
config = chg_hik.CameraConfig()
config.exposure_time = 5000.0  # 5ms
config.gain = 12.5             # 12.5dB
cam.configure(config)
```

**启用自动模式：**
```python
config = chg_hik.CameraConfig()
config.exposure_auto = True
config.gain_auto = True
cam.configure(config)
```

**混合模式（手动曝光 + 自动增益）：**
```python
config = chg_hik.CameraConfig()
config.exposure_time = 8000.0  # 手动曝光
config.gain_auto = True        # 自动增益
cam.configure(config)
```

**只设置曝光：**
```python
config = chg_hik.CameraConfig()
config.exposure_time = 6000.0  # 只设置曝光，增益保持默认
cam.configure(config)
```

---

### capture_images() 函数（传统 API）

单次采集函数，每次调用都会初始化和关闭相机（耗时较长，不推荐频繁使用）。

```python
result = capture_images(
    output_dir: str,
    format: str = "PNG",
    quality: int = 5,
    camera_ip: Optional[str] = None,
    pc_ip: Optional[str] = None
)
```

**参数：**
- `output_dir` (str): 图片输出目录（必需）
- `format` (str): 图像格式（默认 "PNG"）
- `quality` (int): 图像质量（默认 5）
- `camera_ip` (Optional[str]): 相机 IP 地址（可选）
- `pc_ip` (Optional[str]): PC 网卡 IP 地址（可选）

**返回：** dict - 包含以下键值：
- `success` (bool): 采集是否成功
- `cameras_found` (int): 找到的相机数量（仅枚举模式）
- `cameras_initialized` (int): 成功初始化的相机数量
- `images_captured` (int): 成功采集的图片总数
- `message` (str): 结果消息

**示例：**
```python
# IP 直连模式
result = chg_hik.capture_images(
    output_dir="images",
    camera_ip="192.168.1.64",
    pc_ip="192.168.1.100"
)

# 枚举模式
result = chg_hik.capture_images(output_dir="images")

print(f"成功: {result['success']}")
print(f"采集图片数: {result['images_captured']}")
```

---

## 使用场景

### 场景 1：高速连拍（推荐 Camera 类）

```python
import chg_hik

with chg_hik.Camera(output_dir="burst") as cam:
    cam.open(camera_ip="192.168.1.64", pc_ip="192.168.1.100")

    # 连拍 100 张，每张仅需 100-200ms
    for i in range(100):
        img_path = cam.capture()
```

### 场景 2：参数调优测试

```python
import chg_hik

# 测试不同曝光参数
exposure_times = [3000.0, 6000.0, 9000.0]

with chg_hik.Camera(output_dir="test") as cam:
    cam.open(camera_ip="192.168.1.64", pc_ip="192.168.1.100")

    for exp_time in exposure_times:
        config = chg_hik.CameraConfig()
        config.exposure_time = exp_time
        config.gain = 10.0

        cam.configure(config)
        img_path = cam.capture()
        print(f"曝光 {exp_time}μs: {img_path}")
```

### 场景 3：多相机枚举（传统 API）

```python
import chg_hik

# 自动发现并采集所有相机
result = chg_hik.capture_images(output_dir="images")

print(f"找到相机: {result['cameras_found']}")
print(f"采集图片: {result['images_captured']}")
```

### 场景 4：自定义图像格式

```python
import chg_hik

# JPEG 高质量
with chg_hik.Camera(output_dir="jpeg", format="JPEG", quality=95) as cam:
    cam.open(camera_ip="192.168.1.64", pc_ip="192.168.1.100")
    cam.capture()

# PNG 最大压缩
with chg_hik.Camera(output_dir="png", format="PNG", quality=9) as cam:
    cam.open(camera_ip="192.168.1.64", pc_ip="192.168.1.100")
    cam.capture()
```

---

## GigE 网口相机配置

本库默认配置为 **GigE 网口相机**。

### 网络配置要求

1. **IP 地址设置**
   - 相机和 PC 必须在同一网段
   - 示例：相机 `192.168.1.64`，PC `192.168.1.100`
   - 子网掩码：`255.255.255.0`

2. **网络优化**
   - 启用巨型帧（Jumbo Frame），MTU 设置为 9000
   - 增大网卡接收缓冲区
   - 关闭防火墙或添加 GigEVision 协议例外

3. **连通性测试**
   ```bash
   ping 192.168.1.64  # 测试相机是否可达
   ```

### USB 相机切换

如需使用 USB 3.0 相机，需修改 Rust 源码：

编辑 `src/lib.rs` 第 897 行：
```rust
MvEnumDeviceLayerType::UsbDevice,  // 改为 USB 设备
```

重新编译：
```bash
maturin develop --release
```

---

## 常见问题

### 1. 找不到相机

**可能原因：**
- 相机未连接或驱动未安装
- GigE 相机：网络配置错误，不在同一网段
- MVS SDK 未正确安装
- `Env.json` 路径配置错误
- 防火墙阻止了 GigEVision 协议

**解决方法：**
1. 在海康官方软件 MVS 中确认能看到相机
2. 检查 `Env.json` 中的库路径是否正确
3. GigE 相机：
   - 确认相机和 PC 在同一网段（如 `192.168.1.x`）
   - 使用 `ping` 测试相机 IP 是否可达
   - 检查防火墙设置，允许 UDP 3956 端口
   - 确认网线连接状态

### 2. 导入模块失败

**错误：** `ModuleNotFoundError: No module named 'chg_hik'`

**解决方法：**
```bash
# 重新安装
maturin develop --release

# 验证安装
python -c "import chg_hik; print('OK')"
```

### 3. 加载 DLL/SO 失败

**Windows 错误：** `加载库文件失败`
**Linux 错误：** `链接库无法找到`

**解决方法：**
1. 确认 MVS SDK 已安装
2. 检查 `Env.json` 路径（Windows 使用正斜杠 `/`）
3. Windows: 确认 `MvCameraControl.dll` 存在
4. Linux:
   ```bash
   export LD_LIBRARY_PATH=/opt/MVS/lib/64:$LD_LIBRARY_PATH
   ```

### 4. 相机已打开错误

**错误：** `RuntimeError: 相机已经打开`

**原因：** 重复调用 `open()`

**解决方法：**
```python
# 错误示例
cam.open(...)
cam.open(...)  # ❌ 会报错

# 正确示例
cam.open(...)
cam.capture()
cam.close_camera()
cam.open(...)  # ✓ 关闭后可重新打开
```

### 5. 性能对比

**Camera 类 vs capture_images()**

| 操作 | Camera 类 | capture_images() |
|------|----------|------------------|
| 初始化 | 一次（2-3秒） | 每次调用（2-3秒） |
| 拍照 | 100-200ms | 2-3秒 |
| 100张耗时 | ~12秒 | ~250秒 |
| 推荐场景 | 连续拍摄 | 单次采集 |

**建议：** 需要多次拍照时使用 `Camera` 类，性能提升 10-20 倍。

---

## 项目结构

```
hik/
├── Cargo.toml              # Workspace 配置
├── pyproject.toml          # Maturin 配置
├── Env.json                # SDK 路径配置（必需）
├── src/
│   ├── lib.rs              # Python 绑定实现
│   ├── main.rs             # Rust CLI（可选）
│   └── config.rs           # 配置加载
├── hik-rs/                 # FFI 底层库
│   └── src/
│       └── core/
│           └── mvs_sdk/    # MVS SDK 封装
├── camera_example.py       # Camera 类完整示例
├── config_example.py       # CameraConfig 示例
└── example.py              # 传统 API 示例
```

---

## 依赖

### Python
- Python 3.7+

### Rust
- Rust 1.76.0+
- PyO3
- Maturin

### 外部依赖
- 海康威视 MVS SDK（需单独下载安装）

---

## 参考链接

- [海康机器视觉官网](https://www.hikrobotics.com/)
- [MVS SDK 下载](https://www.hikrobotics.com/cn/machinevision/service/download)
- [PyO3 文档](https://pyo3.rs/)
- [Maturin 文档](https://www.maturin.rs/)

## 更新日志

参见 [CHANGELOG.md](CHANGELOG.md)
