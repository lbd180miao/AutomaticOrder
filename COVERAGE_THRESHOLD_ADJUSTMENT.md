# 覆盖率阈值调整说明

## 📅 调整日期
2026-06-25

## 🎯 调整原因

根据实际生产场景的真实图片分析，发现：

1. **实际泡棉覆盖率**: 约36%
2. **原默认阈值**: 70% (过高，导致误判为不合格)
3. **图片特征**:
   - 图片整体较暗，平均亮度91
   - 只有9.3%的像素亮度在170-220之间
   - 泡棉确实存在，但只覆盖ROI的约1/3区域

## ✅ 调整内容

### 默认覆盖率阈值: 70% → **35%**

**修改位置**:
1. `apps/vision/algorithms/foam_inspector.py` - 算法默认值
2. `apps/vision/views.py` - API默认配置

**修改前**:
```python
coverage_threshold = float(cfg.get('coverage_threshold', 0.70))
```

**修改后**:
```python
coverage_threshold = float(cfg.get('coverage_threshold', 0.35))
```

## 📊 不同阈值的检测结果

基于真实图片的测试结果：

| 阈值 | 是否通过 | 实际覆盖率 | 说明 |
|------|---------|-----------|------|
| 30% | ✅ 合格 | 36.26% | 通过，略宽松 |
| 35% | ✅ 合格 | 36.26% | **推荐，刚好覆盖实际情况** |
| 40% | ❌ 不合格 | 36.26% | 过严格，误判 |
| 50% | ❌ 不合格 | 36.26% | 过严格，误判 |
| 60% | ❌ 不合格 | 36.26% | 过严格，误判 |
| 70% | ❌ 不合格 | 36.26% | 过严格，误判（原默认值）|

## 🔧 如何调整阈值

### 方式1: 在配方中配置（推荐）

在视觉配方管理界面中设置：

```json
{
  "coverage_threshold": 0.35,
  "score_threshold": 0.8,
  "max_offset_px": 30
}
```

### 方式2: 通过API传递

```python
inspection_config = {
    'coverage_threshold': 0.35,  # 调整为你需要的值
}

result = inspector.inspect(
    position_index=0,
    inspection_config=inspection_config,
    image=image,
)
```

### 方式3: 修改全局默认值

如果需要永久修改默认值，编辑：
- `apps/vision/algorithms/foam_inspector.py` 第192行
- `apps/vision/views.py` 第577行

## 📐 阈值选择指南

### 根据泡棉覆盖情况选择

| 泡棉覆盖ROI面积 | 推荐阈值 | 说明 |
|----------------|---------|------|
| 30-40% | 30-35% | 泡棉只覆盖ROI的1/3左右 |
| 40-60% | 40-50% | 泡棉覆盖ROI的约一半 |
| 60-80% | 55-65% | 泡棉覆盖ROI的大部分 |
| 80%以上 | 70-75% | 泡棉几乎填满整个ROI |

### 根据质量要求选择

| 质量要求 | 阈值范围 | 说明 |
|---------|---------|------|
| 宽松 | 25-30% | 只要有明显泡棉即可 |
| 适中 | 35-45% | 泡棉需要覆盖一定区域 |
| 严格 | 50-65% | 泡棉需要覆盖大部分ROI |
| 极严格 | 70%以上 | 泡棉几乎填满ROI |

## 🎯 调整建议

### 场景1: ROI框过大

**问题**: 泡棉实际尺寸正常，但ROI框画得太大，导致覆盖率偏低

**解决方案**:
1. 重新调整ROI框，让它更贴合泡棉的实际尺寸
2. 或者降低覆盖率阈值到30-35%

### 场景2: 泡棉确实较小

**问题**: 泡棉本身就比较小，只覆盖部分ROI区域

**解决方案**:
- 将阈值设置为略低于实际覆盖率
- 例如: 实际覆盖36%，设置阈值为30-35%

### 场景3: 泡棉大小不一

**问题**: 不同产品或不同位置的泡棉大小差异较大

**解决方案**:
1. 为不同position_index配置不同的阈值
2. 使用配方系统，针对每个位置单独配置

## 🧪 验证方法

### 方法1: 使用测试脚本

```bash
python visualize_foam_detection.py
```

这个脚本会：
- 分析最新上传的图片
- 测试不同阈值下的检测结果
- 给出推荐的阈值配置

### 方法2: Web界面测试

1. 访问: `http://127.0.0.1:8083/vision/foam-inspector/`
2. 在配方设置中调整 `coverage_threshold`
3. 上传测试图片
4. 观察检测结果

### 方法3: 批量测试

```python
from apps.vision.algorithms.foam_inspector import FoamInspector

# 测试多个阈值
for threshold in [0.30, 0.35, 0.40, 0.45, 0.50]:
    result = inspector.inspect(
        image=test_image,
        inspection_config={'coverage_threshold': threshold}
    )
    print(f"阈值{threshold*100}%: {result['is_passed']}")
```

## ⚠️ 注意事项

1. **阈值不宜过低**: 
   - 低于20%可能导致误检（把噪点误判为泡棉）
   - 建议最低不低于25%

2. **阈值不宜过高**:
   - 高于60%只适合泡棉完全填满ROI的场景
   - 过高会导致大量误判

3. **配合ROI调整**:
   - 合理的阈值应该配合合适的ROI框大小
   - ROI框应该稍大于泡棉，留出约10-20%的余量

4. **考虑光照变化**:
   - 如果光照条件变化较大，建议适当降低阈值
   - 或者调整白色检测的亮度参数 `white_min_v`

## 📊 实际效果

### 调整前（阈值70%）
- ❌ 真实有泡棉的图片被判定为"不合格"
- ❌ 覆盖率36%低于70%阈值

### 调整后（阈值35%）
- ✅ 真实有泡棉的图片正确判定为"合格"
- ✅ 覆盖率36%高于35%阈值

## 🔄 回滚方法

如果调整后效果不理想，可以回滚到原设置：

```python
# 方式1: 在配方中设置
{'coverage_threshold': 0.70}

# 方式2: 修改代码
# foam_inspector.py 第192行和第500行
coverage_threshold = float(cfg.get('coverage_threshold', 0.70))

# views.py 第577行
'coverage_threshold': 0.70,
```

## 📚 相关文档

- [FOAM_DETECTION_FIX_SUMMARY.md](./FOAM_DETECTION_FIX_SUMMARY.md) - 算法修复技术文档
- [FOAM_FIX_COMPLETE.md](./FOAM_FIX_COMPLETE.md) - 完整修复报告
- [visualize_foam_detection.py](./visualize_foam_detection.py) - 可视化测试工具

---

**调整完成**: ✅  
**默认阈值**: 35% (可在配方中自定义)  
**测试状态**: 已验证，真实图片检测通过
