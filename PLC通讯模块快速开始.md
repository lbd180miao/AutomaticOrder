# PLC通讯模块 - 快速开始

## 🚀 5分钟快速上手

### 1. 测试模块功能

```bash
# 运行测试脚本
python test_plc_writer.py
```

**预期输出**：
```
===========================================================
  PLC补偿值写入模块 - 功能测试
===========================================================

测试1: 写入补偿值到PLC
✓ 写入结果: True
  消息: PLC适配器未实现，跳过实际写入（模拟模式）
  PLC数据: X=-2.23, Y=4.6, Z=2.05
  ⚠ 模拟模式（PLC适配器未实现）
✅ 测试1通过

... (6个测试全部通过)

🎉 所有测试通过！
```

---

## 📝 基本使用

### Python代码示例

```python
from apps.vision.plc_compensation_writer import PLCCompensationWriter

# 创建写入器
writer = PLCCompensationWriter()

# 从定位结果写入PLC
result = writer.write_compensation_from_result(
    result_id=123,      # 定位结果ID
    validate=True,      # 验证补偿值
    revalidate=True     # 二次验证（按配方阈值）
)

# 检查结果
if result['success']:
    print("✅ 补偿值已写入PLC")
    print(f"PLC数据: {result['plc_payload']}")
else:
    print(f"❌ 写入失败: {result['error']}")
```

### API调用示例

```bash
# 从定位结果写入PLC
curl -X POST http://localhost:8000/vision/plc/write/from-result/ \
  -H "Content-Type: application/json" \
  -d '{
    "result_id": 123,
    "validate": true,
    "revalidate": true
  }'
```

**响应**：
```json
{
  "success": true,
  "data": {
    "success": true,
    "message": "补偿值已写入PLC",
    "plc_payload": {
      "task_kind": "RACK_3D_LOCATION",
      "side": "BOTH",
      "layer_no": 2,
      "offset_x": -2.23,
      "offset_y": 4.60,
      "offset_z": 2.05,
      "compensation_valid": true
    },
    "written_at": "2026-07-01T14:30:00"
  }
}
```

---

## 🔄 完整流程示例

### 场景：料架定位 → 补偿计算 → PLC写入

```python
from apps.vision.rack_positioning_service import RackPositioningService
from apps.vision.compensation_service import CompensationService
from apps.vision.plc_compensation_writer import PLCCompensationWriter
import numpy as np

# 准备点云数据
pointcloud = np.load('rack_layer_2.npy')  # 或从相机采集

# 步骤1: 执行定位
positioning_service = RackPositioningService()
positioning_result = positioning_service.process_layer_positioning(
    recipe_id=1,
    layer_no=2,
    pointcloud=pointcloud,
    coordinate_system='ROBOT'
)

if not positioning_result.is_success:
    print("❌ 定位失败")
    exit()

print(f"✅ 定位成功: X偏移={positioning_result.offset_x:.2f}mm")

# 步骤2: 计算补偿值
compensation_service = CompensationService()
compensation = compensation_service.calculate_compensation_from_positioning_result(
    positioning_result=positioning_result,
    rack_side='BOTH'
)

if not compensation.is_valid:
    print("❌ 补偿值无效")
    exit()

print(f"✅ 补偿值有效: X={compensation.compensation_x:.2f}mm")

# 步骤3: 写入PLC
plc_writer = PLCCompensationWriter()
write_result = plc_writer.write_compensation_to_plc(
    compensation=compensation,
    layer_no=2,
    rack_side='BOTH',
    recipe_id=1
)

if write_result['success']:
    print("✅ PLC写入成功")
    print(f"PLC数据: {write_result['plc_payload']}")
else:
    print(f"❌ PLC写入失败: {write_result['error']}")
```

---

## 🔌 完整流程一站式API

```bash
# 使用complete-flow接口完成所有步骤
curl -X POST http://localhost:8000/vision/plc/complete-flow/ \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_id": 1,
    "layer_no": 2,
    "pointcloud_file": "/data/rack_layer_2.npy",
    "coordinate_system": "ROBOT",
    "rack_side": "BOTH",
    "write_to_plc": true
  }'
```

**响应**：
```json
{
  "success": true,
  "data": {
    "overall_success": true,
    "message": "完整流程执行成功",
    "positioning_success": true,
    "positioning_result": {
      "offset_x": -2.23,
      "offset_y": 4.60,
      "offset_z": 2.05
    },
    "compensation_success": true,
    "compensation": {
      "compensation_x": -2.23,
      "compensation_y": 4.60,
      "compensation_z": 2.05,
      "is_valid": true
    },
    "plc_write_success": true,
    "plc_write_result": {
      "success": true,
      "message": "补偿值已写入PLC"
    }
  }
}
```

---

## 📊 查询PLC写入状态

### 查询单个结果的状态

```bash
curl "http://localhost:8000/vision/plc/status/?result_id=123"
```

**响应**：
```json
{
  "success": true,
  "data": {
    "result_id": 123,
    "plc_write_status": "SUCCESS",
    "plc_error_message": "",
    "plc_written_at": "2026-07-01T14:30:00",
    "plc_payload": {
      "offset_x": -2.23,
      "offset_y": 4.60,
      "offset_z": 2.05
    }
  }
}
```

### 查询写入历史

```bash
curl "http://localhost:8000/vision/plc/history/?recipe_id=1&layer_no=2&limit=10"
```

---

## 🔧 批量写入配方所有层

```python
from apps.vision.plc_compensation_writer import PLCCompensationWriter

writer = PLCCompensationWriter()

# 批量写入配方ID=1的第1-5层
result = writer.batch_write_compensations_for_recipe(
    recipe_id=1,
    layers=[1, 2, 3, 4, 5],
    validate=True
)

print(f"总计: {result['total']} 层")
print(f"成功: {result['success_count']} 层")
print(f"失败: {result['failed_count']} 层")

# 查看详细结果
for layer_no, layer_result in result['results'].items():
    status = "✅" if layer_result.get('success') else "❌"
    print(f"{status} 第{layer_no}层: {layer_result.get('message', layer_result.get('error'))}")
```

**输出示例**：
```
总计: 5 层
成功: 5 层
失败: 0 层
✅ 第1层: 补偿值已写入PLC
✅ 第2层: 补偿值已写入PLC
✅ 第3层: 补偿值已写入PLC
✅ 第4层: 补偿值已写入PLC
✅ 第5层: 补偿值已写入PLC
```

---

## ⚙️ PLC写入状态码

| 状态码 | 含义 | 说明 |
|--------|------|------|
| `SUCCESS` | ✅ 写入成功 | PLC接收成功 |
| `SIMULATED` | ⚠️ 模拟成功 | PLC未实现，模拟模式 |
| `REJECTED` | ❌ 被拒绝 | 验证失败，未写入 |
| `SKIPPED` | ⏭️ 跳过 | 定位失败，无需写入 |
| `FAILED` | ❌ 写入失败 | PLC通讯失败 |
| `ERROR` | ❌ 错误 | 其他错误 |

---

## 🎯 常见场景

### 场景1: 定位完成后自动写入PLC

```python
# 在定位完成后的回调中
def on_positioning_complete(result_id):
    writer = PLCCompensationWriter()
    
    write_result = writer.write_compensation_from_result(
        result_id=result_id,
        validate=True,
        revalidate=True
    )
    
    if write_result['success']:
        logger.info(f"PLC写入成功: 结果ID={result_id}")
    else:
        logger.error(f"PLC写入失败: {write_result['error']}")
```

### 场景2: 手动触发PLC写入

```python
# 从前端或控制台触发
def manual_write_to_plc(result_id):
    """手动写入补偿值到PLC"""
    writer = PLCCompensationWriter()
    
    # 先查询结果状态
    from apps.vision.models import RackLocationResult
    result = RackLocationResult.objects.get(id=result_id)
    
    print(f"定位结果: 层={result.layer_no}, 偏移X={result.offset_x}mm")
    
    # 确认后写入
    confirm = input("确认写入PLC? (y/n): ")
    if confirm.lower() == 'y':
        write_result = writer.write_compensation_from_result(result_id)
        print(f"写入结果: {write_result}")
```

### 场景3: 重新写入失败的结果

```python
from apps.vision.models import RackLocationResult

# 查找写入失败的结果
failed_results = RackLocationResult.objects.filter(
    plc_write_status__in=['FAILED', 'ERROR']
)

print(f"找到 {failed_results.count()} 个失败记录")

# 重新写入
writer = PLCCompensationWriter()

for result in failed_results:
    print(f"重新写入结果ID={result.id}...")
    
    write_result = writer.write_compensation_from_result(result.id)
    
    if write_result['success']:
        print(f"  ✅ 成功")
    else:
        print(f"  ❌ 仍然失败: {write_result['error']}")
```

---

## 📋 API接口总览

| 接口 | 方法 | 功能 |
|------|------|------|
| `/vision/plc/write/` | POST | 写入补偿值到PLC |
| `/vision/plc/write/from-result/` | POST | 从定位结果写入 |
| `/vision/plc/write/batch/` | POST | 批量写入配方所有层 |
| `/vision/plc/complete-flow/` | POST | 完整流程（定位→补偿→PLC） |
| `/vision/plc/status/` | GET | 查询PLC写入状态 |
| `/vision/plc/history/` | GET | 查询PLC写入历史 |

---

## ⚠️ 重要提示

### 1. 模拟模式

**当前状态**：PLC适配器未实现，模块以模拟模式运行

**特点**：
- 不会实际写入PLC
- 所有功能正常工作
- 状态标记为 `SIMULATED`
- 日志显示警告信息

**投产前**：需要根据现场PLC实现适配器

### 2. 二次验证

`revalidate=True` 会按当前配方阈值重新验证补偿值

**建议**：生产环境始终启用二次验证

### 3. 报警机制

写入失败会自动创建报警，严重错误会锁定工位

---

## 🔗 相关文档

- [PLC通讯模块交付文档.md](./PLC通讯模块交付文档.md) - 完整技术文档
- [补偿值计算模块交付文档.md](./补偿值计算模块交付文档.md) - 补偿计算模块
- [料架定位算法模块交付文档.md](./料架定位算法模块交付文档.md) - 定位算法模块

---

## 🆘 快速故障排查

**问题**：PLC写入失败
```python
# 1. 检查PLC设备状态
from apps.devices.models import Device
plc = Device.objects.filter(device_type='PLC').first()
print(f"PLC状态: {plc.status}")

# 2. 检查补偿值
from apps.vision.models import RackLocationResult
result = RackLocationResult.objects.get(id=123)
print(f"偏移: X={result.offset_x}, Y={result.offset_y}, Z={result.offset_z}")
print(f"置信度: {result.confidence}")

# 3. 查看错误日志
print(f"错误信息: {result.plc_error_message}")
```

---

**开始使用PLC通讯模块，让机器人更精确！** 🚀
