# API测试指南 - ROI自动保存和复用功能

## 测试环境准备

1. 确保Django服务正在运行
2. 准备一个测试配方（可以通过管理后台或API创建）
3. 准备API测试工具（Postman、curl或其他）

## API接口清单

### 1. 获取配方详情（含ROI信息）

**新增接口**

```
GET /api/rack-location/recipes/<recipe_id>/
```

**请求示例**：
```bash
curl -X GET http://localhost:8000/api/rack-location/recipes/1/
```

**响应示例**：
```json
{
  "success": true,
  "recipe": {
    "id": 1,
    "recipe_name": "3D-L1",
    "layer_no": 1,
    "standard_x": 1100.0,
    "standard_y": 600.0,
    "standard_z": 850.0,
    "roi_config": {
      "coordinate_system": "robot",
      "target_roi": {
        "x": 100,
        "y": 200,
        "w": 300,
        "h": 400
      },
      "target_roi_updated_at": "2026-07-02T10:30:00.123456+08:00"
    },
    "roi_info": {
      "has_saved_roi": true,
      "target_roi": {
        "x": 100,
        "y": 200,
        "w": 300,
        "h": 400
      },
      "roi_updated_at": "2026-07-02T10:30:00.123456+08:00"
    }
  }
}
```

### 2. 工作台计算偏差（自动加载ROI）

**接口**：
```
POST /api/rack-location/workbench/calculate/
```

**测试场景A：使用新绘制的ROI**

```bash
curl -X POST http://localhost:8000/api/rack-location/workbench/calculate/ \
  -H "Content-Type: application/json" \
  -d '{
    "pointcloud_token": "vision/rack_workbench/2026/07/02/rack_workbench_103000_123456.npy",
    "recipe_id": 1,
    "layer_no": 1,
    "roi_config": {
      "target_roi": {
        "x": 150,
        "y": 250,
        "w": 350,
        "h": 450
      }
    }
  }'
```

**测试场景B：不传ROI，自动加载已保存的ROI**

```bash
curl -X POST http://localhost:8000/api/rack-location/workbench/calculate/ \
  -H "Content-Type: application/json" \
  -d '{
    "pointcloud_token": "vision/rack_workbench/2026/07/02/rack_workbench_103000_123456.npy",
    "recipe_id": 1,
    "layer_no": 1,
    "roi_config": {}
  }'
```

**预期行为**：
- 场景A：使用传入的新ROI进行计算
- 场景B：后端自动从配方加载已保存的ROI进行计算，日志中会输出"自动加载配方 X 的已保存ROI坐标"

### 3. 工作台保存结果（自动保存ROI）

**接口**：
```
POST /api/rack-location/workbench/save/
```

**测试场景：保存结果并自动保存ROI坐标**

```bash
curl -X POST http://localhost:8000/api/rack-location/workbench/save/ \
  -H "Content-Type: application/json" \
  -d '{
    "pointcloud_token": "vision/rack_workbench/2026/07/02/rack_workbench_103000_123456.npy",
    "recipe_id": 1,
    "layer_no": 1,
    "roi_config": {
      "target_roi": {
        "x": 150,
        "y": 250,
        "w": 350,
        "h": 450
      }
    }
  }'
```

**预期行为**：
- 保存计算结果到数据库
- 自动将ROI坐标保存到配方的`roi_config`字段
- 日志中输出"已保存配方 X 的ROI坐标: {...}"
- 保存时间戳到`target_roi_updated_at`字段

## 完整测试流程

### 步骤1：创建测试配方

```bash
curl -X POST http://localhost:8000/api/rack-location/recipes/ \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "测试配方-ROI自动保存",
    "layer_no": 1,
    "layer_count": 3,
    "standard_x": 1100,
    "standard_y": 600,
    "standard_z": 850,
    "enabled": true
  }'
```

**记录返回的recipe_id，用于后续测试**

### 步骤2：采集点云

```bash
curl -X POST http://localhost:8000/api/rack-location/workbench/capture/ \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_id": 1
  }'
```

**记录返回的pointcloud_token**

### 步骤3：首次计算（传入ROI）

```bash
curl -X POST http://localhost:8000/api/rack-location/workbench/calculate/ \
  -H "Content-Type: application/json" \
  -d '{
    "pointcloud_token": "<从步骤2获取>",
    "recipe_id": 1,
    "layer_no": 1,
    "roi_config": {
      "target_roi": {
        "x": 100,
        "y": 200,
        "w": 300,
        "h": 400
      }
    }
  }'
```

### 步骤4：保存结果（自动保存ROI）

```bash
curl -X POST http://localhost:8000/api/rack-location/workbench/save/ \
  -H "Content-Type: application/json" \
  -d '{
    "pointcloud_token": "<从步骤2获取>",
    "recipe_id": 1,
    "layer_no": 1,
    "roi_config": {
      "target_roi": {
        "x": 100,
        "y": 200,
        "w": 300,
        "h": 400
      }
    }
  }'
```

### 步骤5：验证ROI已保存

```bash
curl -X GET http://localhost:8000/api/rack-location/recipes/1/
```

**检查响应**：
- `roi_info.has_saved_roi` 应该为 `true`
- `roi_info.target_roi` 应该包含步骤4保存的ROI坐标
- `roi_info.roi_updated_at` 应该有时间戳

### 步骤6：再次采集点云

```bash
curl -X POST http://localhost:8000/api/rack-location/workbench/capture/ \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_id": 1
  }'
```

**记录新的pointcloud_token**

### 步骤7：第二次计算（不传ROI，测试自动加载）

```bash
curl -X POST http://localhost:8000/api/rack-location/workbench/calculate/ \
  -H "Content-Type: application/json" \
  -d '{
    "pointcloud_token": "<从步骤6获取>",
    "recipe_id": 1,
    "layer_no": 1,
    "roi_config": {}
  }'
```

**预期结果**：
- 计算成功，使用步骤4保存的ROI坐标
- 查看后端日志，应该有"自动加载配方 1 的已保存ROI坐标"

### 步骤8：更新ROI坐标

```bash
curl -X POST http://localhost:8000/api/rack-location/workbench/save/ \
  -H "Content-Type: application/json" \
  -d '{
    "pointcloud_token": "<从步骤6获取>",
    "recipe_id": 1,
    "layer_no": 1,
    "roi_config": {
      "target_roi": {
        "x": 150,
        "y": 250,
        "w": 350,
        "h": 450
      }
    }
  }'
```

### 步骤9：验证ROI已更新

```bash
curl -X GET http://localhost:8000/api/rack-location/recipes/1/
```

**检查响应**：
- `roi_info.target_roi` 应该更新为新的坐标
- `roi_info.roi_updated_at` 时间戳应该更新

## 验证点清单

- [ ] 创建配方时，`roi_config`为空对象
- [ ] 首次保存ROI后，配方的`roi_config`包含`target_roi`
- [ ] ROI保存时，`target_roi_updated_at`字段被正确设置
- [ ] 获取配方详情时，`roi_info`正确反映ROI状态
- [ ] 计算时不传ROI，能自动从配方加载已保存的ROI
- [ ] 计算时传入新ROI，使用新的ROI而非已保存的
- [ ] 更新ROI后，旧的ROI被新的覆盖
- [ ] 后端日志正确输出保存和加载的信息

## 错误场景测试

### 场景1：没有保存ROI，也不传ROI

```bash
# 先创建一个没有ROI的配方
curl -X POST http://localhost:8000/api/rack-location/recipes/ \
  -H "Content-Type: application/json" \
  -d '{
    "recipe_name": "无ROI配方",
    "layer_no": 2,
    "enabled": true
  }'

# 采集点云
# ...

# 尝试计算，不传ROI
curl -X POST http://localhost:8000/api/rack-location/workbench/calculate/ \
  -H "Content-Type: application/json" \
  -d '{
    "pointcloud_token": "<token>",
    "recipe_id": <新配方ID>,
    "layer_no": 2,
    "roi_config": {}
  }'
```

**预期结果**：
- 返回错误："请先绘制 ROI"
- 状态码：400

### 场景2：Token失效

```bash
curl -X POST http://localhost:8000/api/rack-location/workbench/calculate/ \
  -H "Content-Type: application/json" \
  -d '{
    "pointcloud_token": "invalid/token.npy",
    "recipe_id": 1,
    "layer_no": 1,
    "roi_config": {}
  }'
```

**预期结果**：
- 返回错误："点云数据已失效，请重新采集"
- 状态码：400

## 日志检查

测试过程中，查看Django日志应该能看到：

```
[INFO] 已保存配方 1 的ROI坐标: {'x': 100, 'y': 200, 'w': 300, 'h': 400}
[INFO] 自动加载配方 1 的已保存ROI坐标
```

## 数据库验证

可以直接查询数据库验证：

```sql
-- 查看配方的ROI配置
SELECT id, recipe_name, roi_config 
FROM vision_rack_location_recipe 
WHERE id = 1;

-- roi_config字段应该包含：
-- {
--   "coordinate_system": "robot",
--   "target_roi": {...},
--   "target_roi_updated_at": "2026-07-02T..."
-- }
```

## 性能测试

测试大量调用时的性能：

```bash
# 使用脚本循环调用100次
for i in {1..100}; do
  curl -X POST http://localhost:8000/api/rack-location/workbench/calculate/ \
    -H "Content-Type: application/json" \
    -d '{...}'
  echo "第 $i 次调用完成"
done
```

**验证点**：
- 响应时间稳定
- 内存使用正常
- 没有资源泄漏

---

**测试完成后，记得清理测试数据！**
