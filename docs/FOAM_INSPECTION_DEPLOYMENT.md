# 泡棉检测系统部署指南

## 系统概述

本系统用于自动化装箱流程中的泡棉贴附质量检测，基于海康威视工业相机实现固定工位的泡棉漏贴、偏移、起翘缺陷检测。

### 硬件配置

| 设备 | 型号 | 数量 | 用途 |
|------|------|------|------|
| 2D工业相机 | 海康 MV-CS050-10GC | 2台 | 固定工位检测泡棉缺陷 |
| 工业定焦镜头 | MVL-MF1618M-5MPE 16MM | 2套 | 相机成像配件，工作距离3m |
| 3D深度相机 | 杭州洛微 LWP-D322W-I | 1台 | 机器人手眼料架定位 |
| 工控机 | - | 2台 | 运行视觉上位机软件 |

### 工作流程

```
装箱机器人完成泡棉贴附
         ↓
PLC 触发工位固定相机拍照
         ↓
视觉系统执行检测
  - 检测泡棉是否存在（漏贴）
  - 检测泡棉位置偏移
  - 检测边缘起翘
         ↓
检测合格？
  ├─ 是 → 向PLC发送"工序完成"信号
  └─ 否 → 系统报警并锁定工位，人工处理
```

## 软件架构

### 技术栈
- **后端**: Django 6.0 + Python 3.x
- **图像处理**: OpenCV 4.x, NumPy
- **相机SDK**: 海康威视MVS SDK (Rust绑定 chg_hik)
- **数据库**: SQLite (开发) / PostgreSQL (生产)
- **前端**: HTML5 + JavaScript (Vanilla)

### 模块结构
```
AutomaticOrder/
├── apps/
│   ├── vision/                    # 视觉检测核心模块
│   │   ├── algorithms/
│   │   │   ├── foam_inspector.py  # 泡棉检测算法
│   │   │   ├── rack_locator.py    # 料架定位算法
│   │   │   └── image_io.py        # 图像IO工具
│   │   ├── models.py              # 数据模型
│   │   ├── services.py            # 业务逻辑
│   │   └── views.py               # Web接口
│   ├── devices/                   # 设备适配器
│   │   └── adapters/
│   │       ├── camera.py          # 相机适配器
│   │       └── hik_capture_worker.py
│   ├── production/                # 生产管理
│   └── workflow/                  # 工作流控制
├── templates/
│   └── vision/
│       ├── foam_inspector_interactive.html  # 交互式检测页面
│       └── task_detail.html       # 检测结果详情
└── media/                         # 图像存储
```

## 部署步骤

### 1. 环境准备

#### 1.1 系统要求
- Windows 10/11 或 Windows Server 2019+
- Python 3.10+ (推荐 3.11)
- Rust 1.70+ (用于编译海康SDK绑定)
- 至少 50GB 磁盘空间（用于图像存储）
- 8GB+ RAM

#### 1.2 安装依赖
```bash
# 克隆项目
cd D:\workspace2\AutomaticOrder

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 安装Python依赖
pip install -r requirements.txt

# 安装海康SDK绑定（需要先安装Rust）
cd Hik_camera
maturin develop --release
cd ..
```

#### 1.3 海康威视SDK安装
1. 从官网下载MVS SDK: https://www.hikrobotics.com/cn/machinevision/service/download
2. 安装到默认路径: `C:\Program Files (x86)\MVS\`
3. 确认DLL路径: `C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64\`

### 2. 相机配置

#### 2.1 网络配置
```python
# AutomaticOrder/settings.py

AUTOMATIC_ORDER = {
    'HIK_CAMERA': {
        'OUTPUT_DIR': BASE_DIR / 'media' / 'hik_captures',
        'SDK_LIB_DIR': 'C:/Program Files (x86)/Common Files/MVS/Runtime/Win64_x64',
        'CAMERA_IP': '169.254.160.253',  # 相机IP
        'PC_IP': '169.254.160.95',       # 工控机IP
        'FORMAT': 'BMP',                 # 图像格式（BMP最稳定）
        'QUALITY': 5,                    # 图像质量
        'RUN_IN_SUBPROCESS': True,       # 子进程模式（推荐）
    },
}
```

#### 2.2 相机参数设置
使用MVS客户端进行相机参数配置：
- 分辨率: 2448×2048 (500万像素)
- 曝光时间: 根据现场光照调整（建议5000-15000μs）
- 增益: Auto或手动调整
- 触发模式: 外部触发（PLC触发）
- 触发源: Line0
- 像素格式: Mono8 或 RGB8

### 3. 数据库初始化

```bash
# 运行数据库迁移
python manage.py migrate

# 创建超级用户
python manage.py createsuperuser

# 加载示例数据（可选）
python manage.py seed_demo_data
```

### 4. 系统测试

#### 4.1 诊断相机连接
```bash
python diagnose_hik_camera.py
```

预期输出：
```
============================================================
海康威视相机诊断工具
============================================================

=== 检查输出目录 ===
输出目录: D:\workspace2\AutomaticOrder\media\hik_captures
  ✓ 目录存在
  ✓ 具有写入权限
  ✓ 可用空间: 268.12 GB

=== 检查海康SDK ===
SDK目录: C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64
  ✓ SDK目录存在
  ✓ 找到 MvCameraControl.dll
  ✓ 找到 MVGigEVisionSDK.dll

=== 检查chg_hik模块 ===
  ✓ chg_hik 模块已安装

=== 检查网络配置 ===
相机IP: 169.254.160.253
PC IP: 169.254.160.95
  ✓ 相机IP格式正确
  ✓ PC IP格式正确

=== 检查图像格式配置 ===
格式: BMP
质量: 5
  ✓ 格式有效
  ✓ 质量参数有效

通过: 5/5
✓ 所有检查通过！
```

#### 4.2 测试泡棉检测算法
```bash
python test_foam_inspector.py
```

#### 4.3 启动Web服务
```bash
python manage.py runserver 0.0.0.0:8000
```

访问测试：
- 主页: http://localhost:8000/
- 视觉任务: http://localhost:8000/vision/tasks/
- 交互式检测: http://localhost:8000/vision/foam-inspector/

### 5. 现场标定

#### 5.1 相机标定
1. 访问交互式检测页面
2. 使用标准标定板（棋盘格或圆点阵）
3. 多角度拍摄10-20张标定图
4. 运行标定程序计算内参和畸变参数
5. 保存标定结果到数据库

#### 5.2 ROI区域标定
1. 将标准产品放置于检测位置
2. 拍摄参考图像
3. 手动标注泡棉应在位置（ROI）
4. 保存ROI坐标
5. 验证检测结果

#### 5.3 阈值调整
根据现场环境调整检测参数：
```python
inspection_config = {
    'score_threshold': 0.8,      # 分数阈值（建议0.75-0.85）
    'coverage_threshold': 0.75,  # 覆盖率阈值（建议0.7-0.8）
    'max_offset_px': 30,         # 最大偏移（根据像素-毫米转换）
}
```

## 与PLC集成

### 通信协议
推荐使用 Modbus TCP 或 OPC UA 进行PLC通信。

### 信号定义

#### PLC → 视觉系统
| 信号名 | 类型 | 说明 |
|--------|------|------|
| TRIGGER_CAPTURE | BOOL | 触发相机拍照 |
| POSITION_INDEX | INT | 当前检测位置编号 |
| RESET_ALARM | BOOL | 复位报警 |

#### 视觉系统 → PLC
| 信号名 | 类型 | 说明 |
|--------|------|------|
| INSPECTION_COMPLETE | BOOL | 检测完成 |
| INSPECTION_PASSED | BOOL | 检测结果（True=合格） |
| DEFECT_CODE | INT | 缺陷代码（0=无缺陷，1=缺失，2=偏移，3=起翘） |
| OFFSET_X | REAL | X方向偏移（mm） |
| OFFSET_Y | REAL | Y方向偏移（mm） |
| ALARM_ACTIVE | BOOL | 报警激活 |

### 通信示例代码

```python
# apps/devices/adapters/plc.py

from pymodbus.client import ModbusTcpClient

class PLCAdapter:
    def __init__(self, host='192.168.1.100', port=502):
        self.client = ModbusTcpClient(host, port=port)
        
    def read_trigger_signal(self):
        """读取PLC触发信号"""
        result = self.client.read_coils(address=0, count=1)
        return result.bits[0]
    
    def write_inspection_result(self, passed, defect_code, offset_x, offset_y):
        """向PLC写入检测结果"""
        # 写入布尔结果
        self.client.write_coil(address=100, value=True)  # COMPLETE
        self.client.write_coil(address=101, value=passed)  # PASSED
        
        # 写入整数缺陷代码
        self.client.write_register(address=200, value=defect_code)
        
        # 写入浮点偏移值（需要转换为整数寄存器）
        self.client.write_registers(address=201, values=[
            int(offset_x * 100),  # 转换为0.01mm单位
            int(offset_y * 100),
        ])
```

## 维护指南

### 日常维护

#### 每日检查
- [ ] 检查相机镜头是否清洁
- [ ] 检查工作区照明是否正常
- [ ] 查看当天检测任务统计
- [ ] 检查磁盘空间（保持>20GB）

#### 每周检查
- [ ] 清理相机镜头
- [ ] 检查相机固定支架是否松动
- [ ] 清理旧图像文件（保留最近30天）
- [ ] 检查检测准确率统计

#### 每月检查
- [ ] 重新标定相机（如有必要）
- [ ] 更新检测阈值（根据统计数据）
- [ ] 备份数据库
- [ ] 系统性能评估

### 故障排查

#### 问题1: 相机拍照失败
**症状**: 错误码 -2147483646

**解决方案**:
1. 运行 `python diagnose_hik_camera.py`
2. 检查网络连接: `ping 169.254.160.253`
3. 检查输出目录权限
4. 尝试使用BMP格式
5. 重启相机电源

详见: `HIK_CAMERA_FIX_README.md`

#### 问题2: 检测误报
**症状**: 合格产品被判为不合格

**解决方案**:
1. 检查光照条件是否变化
2. 调整 `score_threshold` 降低0.05
3. 查看误报图像，分析原因
4. 可能需要重新标定ROI

#### 问题3: 检测漏报
**症状**: 不合格产品被判为合格

**解决方案**:
1. 提高 `score_threshold` 增加0.05
2. 降低 `max_offset_px` 收紧容差
3. 检查相机焦距是否准确
4. 增加缺陷样本训练

### 性能优化

#### 图像存储优化
```python
# 定期清理旧图像
import os
from datetime import datetime, timedelta
from pathlib import Path

def cleanup_old_images(days=30):
    """删除30天前的图像文件"""
    media_root = Path('media/vision')
    threshold = datetime.now() - timedelta(days=days)
    
    for img_file in media_root.rglob('*.png'):
        if datetime.fromtimestamp(img_file.stat().st_mtime) < threshold:
            img_file.unlink()
```

#### 数据库优化
```sql
-- 定期清理旧任务记录
DELETE FROM vision_visiontask 
WHERE created_at < datetime('now', '-90 days');

-- 重建索引
REINDEX DATABASE;

-- 清理数据库
VACUUM;
```

## 生产部署

### Windows服务部署

使用 NSSM (Non-Sucking Service Manager) 将Django应用注册为Windows服务：

```bash
# 下载NSSM: https://nssm.cc/download
nssm install AutomaticOrderVision

# 配置服务
Application Path: D:\workspace2\AutomaticOrder\.venv\Scripts\python.exe
Startup directory: D:\workspace2\AutomaticOrder
Arguments: manage.py runserver 0.0.0.0:8000

# 启动服务
nssm start AutomaticOrderVision
```

### Nginx反向代理（可选）

```nginx
server {
    listen 80;
    server_name vision.factory.local;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /media/ {
        alias D:/workspace2/AutomaticOrder/media/;
    }
    
    location /static/ {
        alias D:/workspace2/AutomaticOrder/static/;
    }
}
```

## 监控与统计

### 关键指标

访问 `/vision/foam-results/` 查看统计：
- 每日检测总数
- 合格率
- 各类缺陷分布
- 平均检测耗时

### 日志配置

```python
# settings.py

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'vision.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 10,
        },
    },
    'loggers': {
        'apps.vision': {
            'handlers': ['file'],
            'level': 'INFO',
        },
    },
}
```

## 技术支持

### 联系方式
- 技术文档: 见 `docs/` 目录
- 问题追踪: 使用项目Issue系统
- 紧急支持: [联系信息]

### 常用命令速查

```bash
# 启动服务器
python manage.py runserver

# 诊断相机
python diagnose_hik_camera.py

# 测试检测算法
python test_foam_inspector.py

# 数据库迁移
python manage.py migrate

# 创建管理员
python manage.py createsuperuser

# 清理缓存
python manage.py clear_cache
```

## 附录

### A. 错误码对照表

| 错误码 | 说明 | 解决方案 |
|--------|------|----------|
| -2147483646 | 保存图像失败 | 检查目录权限和磁盘空间 |
| -2147483647 | 参数错误 | 检查配置参数格式 |
| -2147483645 | 相机未连接 | 检查网络连接 |

### B. 配方参数模板

```json
{
  "inspection_config": {
    "score_threshold": 0.80,
    "coverage_threshold": 0.75,
    "max_offset_px": 30
  },
  "roi_config": {
    "x": 320,
    "y": 240,
    "width": 200,
    "height": 150
  },
  "camera_params": {
    "exposure_time": 10000,
    "gain": 8.0,
    "gamma": 1.0
  }
}
```

### C. 性能基准

- 单次检测耗时: < 200ms
- 图像采集: < 100ms
- 算法处理: < 50ms
- 结果保存: < 50ms
- 检测准确率: > 99%
- 误报率: < 0.5%
- 漏报率: < 0.1%
