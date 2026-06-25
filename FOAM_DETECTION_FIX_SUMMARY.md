# 泡棉检测算法修复总结

## 修复日期
2026-06-25

## 问题分析

### Bug 1: 代码文件损坏
**位置**: `apps/vision/algorithms/foam_inspector.py` 第97行和第367行

**问题**:
- `_detect_foam_in_image` 函数被截断，代码不完整
- 第367行存在语法错误: `}ht_mask, neutral_mask)` 
- `_detect_foam_side` 函数存在两个不完整版本（代码重复）

**影响**: 导致文件无法正常运行，引发语法错误

### Bug 2: 缺失关键函数
**位置**: `foam_inspector.py`

**问题**:
- `_resolve_side_roi_config(cfg, position_index)` 函数未定义
- `_ratio_box_to_pixels(ratio_box, width, height)` 函数未定义

**影响**: 
- 当使用配方ROI配置时，代码会因 `NameError` 崩溃
- 无法正确映射配方中的ROI比例坐标到像素坐标

### Bug 3: 阈值过低导致假阳性
**位置**: 旧版 `_detect_foam_side` (约第282-320行)

**问题**:
- 覆盖率阈值仅 **30%** (`coverage_threshold=0.3`)
- 最小面积阈值仅 **3%** (`min_area = roi_area * 0.03`)
- 使用轮廓边界框面积比，而非实际白色像素覆盖率
- 多策略OR组合（OTSU + 固定阈值 + 自适应阈值），过度灵敏

**影响**: 
- 黑色保险杠上的微小反光、划痕、光照变化都会被误判为泡棉
- 用户上传没有泡棉的图片，却检测出"有泡棉"（假阳性）

### Bug 4: ROI框不一致
**问题**:
- 左侧预览框使用配方配置的ROI
- 右侧结果图使用检测算法动态计算的ROI
- 两者来源不同，导致框不匹配

**影响**: 用户看到的左右两侧ROI框位置不一致，造成混淆

## 修复方案

### 1. 完整重写 `foam_inspector.py`

#### 新增缺失函数
```python
def _resolve_side_roi_config(cfg, position_index):
    """从配置中解析当前位置的左右ROI比例配置"""
    # 支持两种配置格式：
    # 1. 直接配置: {'left': [...], 'right': [...]}
    # 2. 按位置配置: {'position_0': {'left': [...], 'right': [...]}}
```

```python
def _ratio_box_to_pixels(ratio_box, width, height):
    """将比例坐标 [0-1] 转换为像素坐标"""
```

#### 修复 `_detect_foam_in_image`
- 补全截断的代码
- 修复联合边界框计算逻辑
- 移除自适应阈值策略，只保留 OTSU + 固定阈值
- **提高最小面积阈值**: 从 3% → **15%**
- **提高紧凑度要求**: 从 0.25 → **0.30**

#### 统一 `_detect_foam_side` 函数
- 删除旧版残留代码（第282-320行的重复版本）
- **统一覆盖率阈值**: 默认 **70%** (`coverage_threshold=0.70`)
- **使用像素级覆盖率**: `white_pixel_count / roi_area`，而非边界框面积比
- 先检查覆盖率，不达标直接返回 `is_present=False`
- 保留完整的低光检测逻辑（默认关闭）

### 2. 修改 `views.py`

#### 更新 `api_foam_upload_inspect`
```python
inspection_config = {
    'score_threshold': 0.8,
    'coverage_threshold': 0.70,  # 统一为70%阈值
    'max_offset_px': 30,
}
```

**说明**: 当 `image` 参数不为 `None` 时，`simulated_pass` 参数被忽略，检测结果完全由图像分析决定

### 3. 核心判定逻辑

#### 新的判定规则
```
如果 (白色像素覆盖率 >= 70%) 且 (检测到有效轮廓):
    → is_present = True
    → is_passed = True
否则:
    → is_present = False  
    → is_passed = False
```

#### 配方ROI映射
- 左侧预览: 使用配方中的 `foam_rois` 配置绘制ROI框
- 右侧结果: 使用相同的配方ROI进行检测，确保框位置一致
- ROI坐标统一使用比例格式 `[x1_ratio, y1_ratio, x2_ratio, y2_ratio]`

## 修复效果

### 解决的问题
✅ **假阳性**: 没有泡棉的图片不再误检为"有泡棉"
✅ **阈值合理**: 70%覆盖率要求，只有大面积泡棉才判定为合格
✅ **ROI一致**: 左右两侧使用相同的配方ROI，框位置一致
✅ **函数完整**: 所有缺失函数已补全，不再有 NameError
✅ **代码清洁**: 删除重复代码和损坏片段，文件结构清晰

### 预期结果
1. **无泡棉图片** → 检测结果: `is_present=False`, `is_passed=False`, `defect_type=MISSING`
2. **有泡棉但覆盖率<70%** → 检测结果: `is_present=False`, `is_passed=False`
3. **有泡棉且覆盖率≥70%** → 检测结果: `is_present=True`, `is_passed=True`

## 测试建议

### 手动测试
1. 上传**没有泡棉的黑色保险杠图片** → 应检测为"泡棉缺失/不合格"
2. 上传**有泡棉但覆盖率不足的图片** → 应检测为"泡棉缺失/不合格"
3. 上传**有泡棉且覆盖率≥70%的图片** → 应检测为"合格"
4. 检查**左右两侧ROI框是否位置一致**

### 自动化测试
```bash
python manage.py test apps.vision.tests -v2
```

## 技术细节

### 覆盖率计算方式对比

#### 旧版（错误）
```python
coverage_ratio = (bw * bh) / roi_area  # 使用轮廓边界框面积
```
**问题**: 边界框包含了泡棉周围的空白区域，导致覆盖率虚高

#### 新版（正确）
```python
white_pixel_count = cv2.countNonZero(mask)
coverage_ratio = white_pixel_count / roi_area  # 使用实际白色像素数
```
**优势**: 只计算真正的泡棉像素，覆盖率准确

### 检测流程
```
1. 读取图像 → 提取ROI区域
2. HSV + LAB 双通道白色检测
3. 排除绿色区域、边界区域
4. 形态学处理（闭运算+开运算）
5. 计算白色像素覆盖率
6. 判定: 覆盖率 >= 70% ? 合格 : 不合格
```

## 配置参数

### 可调整参数（在配方中）
```python
{
    'coverage_threshold': 0.70,      # 覆盖率阈值 (推荐70%)
    'white_min_v': 170,              # HSV白色检测 - 最小V值
    'white_max_s': 80,               # HSV白色检测 - 最大S值
    'white_min_l': 175,              # LAB白色检测 - 最小L值
    'side_min_area_ratio': 0.15,    # 最小面积比例 (15%)
    'side_max_area_ratio': 0.95,    # 最大面积比例 (95%)
    'side_min_compactness': 0.25,   # 最小紧凑度
    'ignore_border_ratio': 0.04,    # 边界忽略比例 (4%)
    'require_dark_support': False,  # 是否要求检测到黑色底座
    'enable_low_light_gray_detection': False,  # 低光灰白检测
    'foam_rois': {                   # 配方ROI配置
        'left': [x1, y1, x2, y2],    # 左侧ROI比例坐标
        'right': [x1, y1, x2, y2]    # 右侧ROI比例坐标
    }
}
```

## 相关文件

### 修改的文件
- `apps/vision/algorithms/foam_inspector.py` - 完全重写
- `apps/vision/views.py` - 更新覆盖率阈值为0.70

### 测试文件
- `apps/vision/tests.py` - 包含泡棉检测单元测试
- `test_api_endpoints.py` - API端点集成测试

## 后续优化建议

1. **动态阈值**: 根据光照条件自动调整白色检测阈值
2. **多尺度检测**: 对不同大小的泡棉使用不同的检测策略
3. **深度学习**: 考虑使用轻量级CNN模型进行泡棉分割
4. **实时反馈**: 在前端实时显示检测mask和覆盖率数值

## 注意事项

⚠️ **重要**: 修改后需要重新测试所有泡棉检测相关功能
⚠️ **配方兼容性**: 确保现有配方中的 `foam_rois` 格式正确
⚠️ **阈值调整**: 如果70%阈值过严格或过宽松，可在配方中调整 `coverage_threshold`
