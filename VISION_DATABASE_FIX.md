# Vision 数据库错误修复说明

## 问题描述

访问 `/vision/tasks/` 页面时出现 `OperationalError` 错误：

```
django.db.utils.OperationalError: no such column: vision_racklocationresult.actual_x
```

## 根本原因

`RackLocationResult` 模型中的三个字段 (`actual_x`, `actual_y`, `actual_z`) 在数据库表中缺失。虽然迁移文件 `0005_racklocationresult_confidence_and_more.py` 中包含了这些字段，但由于某种原因（可能是迁移执行时的问题或数据库状态不一致），这三个列没有被正确添加到数据库表中。

## 已修复内容

### 1. 创建补丁迁移 (`0006_add_actual_coordinates.py`)

手动创建了一个新的迁移文件，专门添加缺失的三个字段：

```python
migrations.AddField(
    model_name='racklocationresult',
    name='actual_x',
    field=models.DecimalField(decimal_places=3, default=0, max_digits=10),
),
migrations.AddField(
    model_name='racklocationresult',
    name='actual_y',
    field=models.DecimalField(decimal_places=3, default=0, max_digits=10),
),
migrations.AddField(
    model_name='racklocationresult',
    name='actual_z',
    field=models.DecimalField(decimal_places=3, default=0, max_digits=10),
),
```

### 2. 优化视图查询错误处理

改进了 `task_list` 视图函数，增加了多层次的错误处理：

- 第一级：尝试使用 `select_related` 和 `prefetch_related` 的完整查询
- 第二级：如果失败，尝试不使用 `select_related` 的查询
- 第三级：如果仍然失败，尝试基本查询
- 第四级：如果全部失败，返回空列表并显示错误信息

```python
def task_list(request):
    """视觉任务列表页面，显示最近200条任务记录"""
    try:
        tasks = (
            VisionTask.objects
            .select_related('product', 'rack')
            .prefetch_related('images', 'foam_results', 'rack_results')
            .order_by('-created_at')[:200]
        )
        list(tasks[:1])  # 强制执行查询以检测错误
    except Exception as e:
        # 多层次错误处理...
```

### 3. 改进模板的数据访问安全性

更新了 `task_list.html` 模板，使用更安全的方式访问可能为空的外键关系：

```django
<td>
  {% if t.product %}
    {{ t.product.product_code }}
  {% else %}-{% endif %}
</td>
```

### 4. 创建数据库诊断工具

创建了管理命令 `check_vision_db`，用于检查和修复 vision 应用的数据库问题：

```bash
# 检查数据库完整性
python manage.py check_vision_db

# 自动修复检测到的问题
python manage.py check_vision_db --fix
```

该命令会检查：
- 所有必需的数据库表是否存在
- VisionTask 的外键完整性
- 孤立的结果记录
- 显示数据统计信息

### 5. 创建辅助脚本

创建了两个诊断脚本：

1. `check_db_columns.py` - 检查数据库表的实际列结构
2. `test_vision_query.py` - 测试 VisionTask 的查询是否正常工作

## 验证结果

运行 `python test_vision_query.py` 后，所有测试通过：

```
✓ 成功查询到 5 条记录
✓ select_related 查询成功
✓ prefetch_related 查询成功
✓ 查询成功，共 5 条记录
✓ 所有测试通过！/vision/tasks/ 页面应该可以正常工作。
```

## 如何应用修复

如果在其他环境中遇到同样的问题，运行以下命令：

```bash
# 1. 应用迁移
python manage.py migrate vision

# 2. 验证数据库完整性
python manage.py check_vision_db

# 3. 测试查询
python test_vision_query.py
```

## 预防措施

为避免将来出现类似问题：

1. 在修改模型后，始终运行 `python manage.py makemigrations`
2. 应用迁移后，验证表结构是否正确：`python check_db_columns.py`
3. 定期运行 `python manage.py check_vision_db` 检查数据完整性
4. 在生产环境部署前，先在测试环境验证所有迁移

## 技术细节

### RackLocationResult 模型字段

该模型现在包含以下坐标字段：

- `offset_x`, `offset_y`, `offset_z`, `offset_rz` - 偏移量（相对于标准位置）
- `actual_x`, `actual_y`, `actual_z` - 实际测量的绝对坐标值

这些字段用于 3D 深度相机的料架定位功能。

### 数据库迁移历史

1. `0001_initial.py` - 初始模型创建
2. `0002_...` - 字段调整
3. `0003_...` - 泡棉检测结果字段增强
4. `0004_visionrecipe.py` - 视觉配方模型
5. `0005_racklocationresult_confidence_and_more.py` - 料架定位结果增强（部分字段未正确应用）
6. `0006_add_actual_coordinates.py` - 补丁：添加缺失的 actual_x/y/z 字段 ✓

## 问题已解决

现在可以正常访问 `/vision/tasks/` 页面，不会再出现 `OperationalError` 错误。
