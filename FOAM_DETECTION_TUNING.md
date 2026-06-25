# 泡棉检测优化指南

## 🎯 最新优化内容（v2.0）

### 新增功能
1. ✨ **多策略白色检测** - 结合HSV、LAB、OTSU、固定阈值、自适应阈值5种策略
2. 🧠 **智能图像质量分析** - 自动分析亮度、对比度、清晰度、噪声
3. 🔧 **参数自适应调整** - 根据图像质量自动优化检测参数
4. 🎨 **图像增强处理** - 支持对比度增强(CLAHE)和降噪
5. 📊 **详细的质量报告** - 提供完整的图像质量分析和调整建议

## 问题诊断

### 常见问题
1. **误判为NG（右边明明有泡棉）**
   - 原因：覆盖率阈值太高（35%）或白色检测阈值太严格
   - 解决：降低 `coverage_threshold` 到 8%，放宽白色检测参数

2. **检测覆盖率很低（如0.63%）**
   - 原因：ROI区域设置过大，或白色像素识别不足
   - 解决：调整ROI配置或降低白色检测阈值

3. **边缘泡棉检测不到**
   - 原因：边界忽略区域太大
   - 解决：减小 `ignore_border_ratio` 从 4% 到 2%

## 已优化的参数

### 1. 覆盖率阈值（最关键）
```python
# 旧值：0.35 (35%) - 太严格
# 新值：0.08 (8%)  - 适应大ROI场景
'coverage_threshold': 0.08
```

### 2. 白色检测阈值
```python
# HSV - V通道（亮度）
'white_min_v': 150,  # 从170降到150，更容易检测白色

# HSV - S通道（饱和度）
'white_max_s': 100,  # 从80提高到100，允许更多颜色范围

# LAB - L通道（亮度）
'white_min_l': 160,  # 从175降到160，更宽容
```

### 3. 最小面积比例
```python
# 降低最小面积要求，提高检测灵敏度
'side_min_area_ratio': 0.05,  # 从0.15降到0.05 (5%)
'side_max_area_ratio': 0.98,  # 从0.95提高到0.98
```

### 4. 边界忽略区域
```python
# 减小边界忽略，提高边缘检测
'ignore_border_ratio': 0.02,  # 从0.04降到0.02 (2%)
```

### 5. 形态学处理
```python
# 增强闭运算和开运算
- 闭运算核: 9x9, 迭代3次（更好连接断裂区域）
- 开运算核: 5x5, 迭代2次（去除噪点）
```

### 6. 宽高比和紧凑度
```python
# 放宽形状限制
'aspect_ratio': 0.1 ~ 10.0,  # 从0.15-8改为0.1-10
'side_min_compactness': 0.20,  # 从0.25降到0.20
```

## 使用调试工具

### 1. 快速对比测试（推荐）
对比优化前后的检测效果：
```bash
python quick_test_foam.py path/to/image.jpg
```

### 2. 多配置测试
测试不同配置方案：
```bash
python debug_foam_detection.py path/to/image.jpg --position 0
```

### 3. 查看检测步骤
可视化检测的各个中间步骤：
```bash
python debug_foam_detection.py path/to/image.jpg --position 0 --steps
```

这会生成以下中间结果图：
- `01_original.jpg` - 原始图像
- `02_gray.jpg` - 灰度图
- `03_white_hsv.jpg` - HSV白色检测
- `04_white_lab.jpg` - LAB白色检测
- `05_combined.jpg` - 组合结果
- `06_closed.jpg` - 闭运算后
- `07_final.jpg` - 最终mask

### 4. 配置生成器
根据场景生成最佳配置：
```bash
# 交互式模式
python generate_foam_config.py

# 生成指定场景配置
python generate_foam_config.py standard config.json
python generate_foam_config.py low_light config.json
python generate_foam_config.py large_roi config.json

# 生成ROI配置模板
python generate_foam_config.py roi roi_config.json
```

## 配方配置示例

### 🌟 智能自适应配置（推荐）
自动根据图像质量调整参数：
```json
{
  "coverage_threshold": 0.08,
  "white_min_v": 150,
  "white_max_s": 100,
  "white_min_l": 160,
  "side_min_area_ratio": 0.05,
  "side_max_area_ratio": 0.98,
  "ignore_border_ratio": 0.02,
  "enable_quality_analysis": true,
  "enable_auto_adjustment": true
}
```

### 高灵敏度配置（推荐用于大ROI）
```json
{
  "coverage_threshold": 0.05,
  "white_min_v": 140,
  "white_max_s": 110,
  "white_min_l": 150,
  "side_min_area_ratio": 0.03,
  "side_max_area_ratio": 0.98,
  "ignore_border_ratio": 0.01,
  "side_min_compactness": 0.18
}
```

### 标准配置（优化后默认）
```json
{
  "coverage_threshold": 0.08,
  "white_min_v": 150,
  "white_max_s": 100,
  "white_min_l": 160,
  "side_min_area_ratio": 0.05,
  "side_max_area_ratio": 0.98,
  "ignore_border_ratio": 0.02,
  "side_min_compactness": 0.20
}
```

### 严格配置（仅在必要时使用）
```json
{
  "coverage_threshold": 0.20,
  "white_min_v": 165,
  "white_max_s": 90,
  "white_min_l": 170,
  "side_min_area_ratio": 0.10,
  "side_max_area_ratio": 0.95,
  "ignore_border_ratio": 0.03,
  "side_min_compactness": 0.25
}
```

## ROI配置建议

### 左右分离ROI（推荐）
```python
inspection_config = {
    'foam_rois': {
        'position_0': {  # 或使用 '0'
            'left': [0.1, 0.2, 0.45, 0.8],   # [x1_ratio, y1_ratio, x2_ratio, y2_ratio]
            'right': [0.55, 0.2, 0.9, 0.8],
        }
    },
    'coverage_threshold': 0.08,
    # ... 其他参数
}
```

### 单个大ROI
```python
inspection_config = {
    'roi_ratio': [0.05, 0.1, 0.95, 0.9],  # 覆盖整个检测区域
    'coverage_threshold': 0.05,  # 大ROI需要更低的阈值
    # ... 其他参数
}
```

## 参数调优流程

1. **使用调试工具分析当前图像**
   ```bash
   python debug_foam_detection.py your_image.jpg --steps
   ```

2. **查看各步骤的覆盖率数据**
   - 关注"最终mask"的覆盖率
   - 如果覆盖率 < 5%，需要降低白色检测阈值
   - 如果覆盖率 > 15%，可能检测过于宽松

3. **调整配置并测试**
   - 修改配方中的检测参数
   - 重新运行检测
   - 对比结果图

4. **验证多张图片**
   - 使用不同光照条件的图片
   - 确保既不漏检也不误检

## 常见场景配置建议

### 场景1：保险杠背面（黑色背景+白色泡棉）
- 建议：标准配置
- `coverage_threshold`: 0.08
- `white_min_v`: 150
- 对比度高，检测效果好

### 场景2：复杂背景（可能有其他白色物体）
- 建议：严格配置
- `coverage_threshold`: 0.15
- `white_min_v`: 165
- 提高阈值减少误检

### 场景3：光照不足
- 建议：高灵敏度配置
- `coverage_threshold`: 0.05
- `white_min_v`: 140
- 降低阈值提高检测率

### 场景4：ROI特别大（如全图）
- 建议：降低覆盖率阈值
- `coverage_threshold`: 0.03
- ROI越大，泡棉占比越小

## 验证检测效果

### 通过界面查看
- 原图：显示实际拍摄的图像
- 结果图：绿色框=ROI，蓝色框=检测到的泡棉
- 覆盖率数据：检测到的白色像素 / ROI总面积

### 通过日志查看
- 查看 `result_data.coverage_ratio`
- 查看 `result_data.sides`（如果使用左右分离ROI）
- 查看 `reason` 字段（如果检测失败）

## 故障排查

### 问题：右边明明有泡棉，判定为NG
**解决方案：**
1. 检查覆盖率是否低于阈值（如0.63% < 8%）
2. 降低 `coverage_threshold` 到 0.05 或更低
3. 检查ROI是否设置过大
4. 使用调试工具查看白色检测效果

### 问题：检测到的区域太小
**解决方案：**
1. 降低白色检测阈值 `white_min_v`, `white_min_l`
2. 增加 `white_max_s` 允许更多颜色
3. 增强形态学闭运算连接断裂区域
4. 减小边界忽略区域

### 问题：误检其他白色物体
**解决方案：**
1. 提高 `coverage_threshold`
2. 提高 `side_min_area_ratio`
3. 调整ROI精确定位泡棉区域
4. 增加 `side_min_compactness` 要求更紧凑的形状

### 问题：边缘泡棉检测不到
**解决方案：**
1. 减小 `ignore_border_ratio` 到 0.01
2. 调整ROI边界，给泡棉留出足够空间
3. 检查相机位置和角度

## 总结

主要优化点：
1. ✅ **覆盖率阈值从35%降到8%** - 解决大ROI场景误判
2. ✅ **白色检测更宽容** - 提高检测灵敏度
3. ✅ **降低面积限制** - 检测更小的泡棉区域
4. ✅ **减小边界忽略** - 提高边缘检测
5. ✅ **增强形态学处理** - 更好连接断裂区域
6. ✅ **放宽形状限制** - 适应不规则泡棉形状

这些优化应该能解决您遇到的"右边有泡棉但误判为NG"和"覆盖率很低"的问题。


## 新功能详解

### 1. 多策略白色检测

算法现在使用5种策略组合检测白色泡棉：

1. **HSV色彩空间检测** - 基于色调、饱和度、亮度
2. **LAB色彩空间检测** - 基于明度通道
3. **OTSU自适应阈值** - 自动寻找最佳分割阈值
4. **固定高阈值** - 检测明显的白色区域
5. **自适应阈值** - 基于局部对比度

这些策略使用OR逻辑组合，只要任一策略检测到就保留，大幅提高检测率。

### 2. 智能图像质量分析

系统会自动分析：
- **亮度** - 判断光照条件（暗/正常/亮）
- **对比度** - 评估前景背景区分度
- **清晰度** - 基于Laplacian方差
- **噪声水平** - 评估图像噪声
- **白色像素比例** - 初步统计

### 3. 参数自适应调整

根据图像质量分析，系统会自动：

**光照不足时：**
- 降低白色检测阈值 (white_min_v, white_min_l)
- 降低覆盖率要求 (coverage_threshold)
- 启用对比度增强 (use_clahe)

**对比度低时：**
- 启用CLAHE对比度增强
- 降低覆盖率阈值
- 增加形态学处理迭代次数

**图像模糊时：**
- 增强形态学处理
- 连接更多断裂区域

**噪声高时：**
- 启用降噪处理 (denoise)
- 使用非局部均值降噪

### 4. 配置开关

```json
{
  "enable_quality_analysis": true,   // 启用图像质量分析
  "enable_auto_adjustment": true,    // 启用参数自动调整
  "use_clahe": false,                // 手动启用对比度增强
  "denoise": false,                  // 手动启用降噪
  "enable_low_light_gray_detection": false  // 启用低光灰白检测
}
```

## 使用建议流程

### 第一步：快速测试
```bash
# 对比优化效果
python quick_test_foam.py your_image.jpg
```

查看输出，如果新版本检测效果好，直接使用默认配置。

### 第二步：生成场景配置
```bash
# 交互式选择场景
python generate_foam_config.py

# 或直接生成
python generate_foam_config.py large_roi my_config.json
```

### 第三步：配置ROI
```bash
# 生成ROI配置模板
python generate_foam_config.py roi roi_config.json

# 编辑roi_config.json，调整左右ROI的位置和大小
```

### 第四步：细调参数
```bash
# 查看检测步骤，分析哪里需要改进
python debug_foam_detection.py your_image.jpg --steps
```

### 第五步：验证效果
在多张不同条件的图片上测试，确保稳定性。

## 性能优化建议

### 1. ROI配置优先
- 精确配置ROI可以显著提高检测准确性
- 左右分离ROI比单个大ROI效果更好
- 避免ROI包含过多无关区域

### 2. 启用智能自适应
```json
{
  "enable_quality_analysis": true,
  "enable_auto_adjustment": true
}
```
这两个选项可以让系统自动应对不同光照条件。

### 3. 根据场景选择预设
- 标准场景：使用默认配置
- 光照变化大：使用自适应配置
- ROI很大：降低coverage_threshold到0.03-0.05
- 要求严格：使用high_precision配置

### 4. 调试模式
开发阶段建议：
```json
{
  "enable_quality_analysis": true,
  "enable_auto_adjustment": true,
  "save_debug_images": true  // 保存调试图像
}
```

## API使用示例

### 基础使用
```python
from apps.vision.algorithms.foam_inspector import FoamInspector
import cv2

# 初始化检测器
inspector = FoamInspector(simulate=False)

# 读取图像
image = cv2.imread('test.jpg')

# 检测
result = inspector.inspect(
    position_index=0,
    inspection_config={
        'coverage_threshold': 0.08,
        'enable_quality_analysis': True,
        'enable_auto_adjustment': True,
    },
    image=image,
)

# 查看结果
print(f"检测结果: {'PASS' if result['is_passed'] else 'NG'}")
print(f"覆盖率: {result['coverage_ratio']:.2%}")
print(f"置信度: {result['score']:.3f}")

# 查看图像质量分析
if 'quality_analysis' in result:
    qa = result['quality_analysis']
    print(f"亮度: {qa['mean_brightness']}")
    print(f"对比度: {qa['contrast']}")
```

### 使用ROI配置
```python
config = {
    'foam_rois': {
        'position_0': {
            'left': [0.1, 0.2, 0.45, 0.8],
            'right': [0.55, 0.2, 0.9, 0.8],
        }
    },
    'coverage_threshold': 0.08,
    'enable_quality_analysis': True,
}

result = inspector.inspect(
    position_index=0,
    inspection_config=config,
    image=image,
)

# 查看左右侧详细结果
if 'sides' in result.get('result_data', {}):
    for side, data in result['result_data']['sides'].items():
        print(f"{side}: 覆盖率={data['coverage_ratio']:.2%}")
```

## 更新日志

### v2.0 (2026-06-25)
- ✨ 新增多策略白色检测（5种策略组合）
- ✨ 新增智能图像质量分析
- ✨ 新增参数自适应调整
- ✨ 新增图像增强处理（CLAHE、降噪）
- 🔧 降低默认覆盖率阈值 35% → 8%
- 🔧 优化白色检测阈值
- 🔧 改进形态学处理（使用椭圆核）
- 🔧 放宽形状限制
- 📦 新增调试工具和配置生成器

### v1.0 (原始版本)
- 基础泡棉检测功能
- HSV+LAB双策略白色检测
- 左右分离ROI支持

## 常见问题FAQ

**Q: 为什么有些图片还是检测不到？**
A: 尝试：
1. 查看检测步骤 `--steps` 确认白色检测效果
2. 降低 `coverage_threshold` 到 0.03
3. 降低 `white_min_v` 到 140
4. 启用 `use_clahe` 和 `denoise`

**Q: 如何提高检测速度？**
A: 
1. 精确配置ROI，减少检测区域
2. 禁用 `enable_quality_analysis`（如果不需要）
3. 禁用 `denoise`（降噪比较耗时）

**Q: 自适应调整会不会导致误检？**
A: 
- 自适应调整是保守的，只在必要时微调
- 如果担心误检，可设置 `enable_auto_adjustment: false`
- 使用 `high_precision` 预设配置

**Q: 如何调试配置？**
A:
```bash
# 1. 先快速对比
python quick_test_foam.py image.jpg

# 2. 查看检测步骤
python debug_foam_detection.py image.jpg --steps

# 3. 尝试不同配置
python debug_foam_detection.py image.jpg
```

## 联系与支持

如果遇到问题：
1. 查看本文档的故障排查部分
2. 使用调试工具分析问题
3. 尝试不同的预设配置
4. 查看检测步骤可视化结果
