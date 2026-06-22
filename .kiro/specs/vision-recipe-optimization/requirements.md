# 需求文档

## 简介

视觉配方模块优化旨在实现泡棉检测工作台与配方管理模块之间的数据互通，提供用户友好的配方选择、标定、保存和可视化机制。该优化将使用户能够在检测工作台中直接查看、使用和保存配方，无需在多个页面之间反复切换。

## 术语表

- **System**: 视觉配方模块优化系统
- **Workbench**: 泡棉检测工作台（foam_inspector_interactive.html）
- **Recipe_Management_Page**: 配方管理页面（recipe_management.html）
- **VisionRecipe**: 视觉配方数据模型
- **ROI**: 感兴趣区域（Region of Interest），用于定义泡棉检测的矩形区域
- **POS**: 位置索引（Position Index），取值为 0、1 或 2，对应第 1、2、3 层泡棉
- **User**: 系统操作员
- **Camera_Feed**: 相机实时画面
- **Detection_Result**: 检测结果图像
- **Threshold_Config**: 阈值配置，包括覆盖率阈值、得分阈值、偏移阈值

## 需求

### 需求 1: 配方信息在工作台展示

**用户故事:** 作为操作员，我希望在泡棉检测工作台中查看当前 POS 对应的配方信息，以便了解当前检测使用的参数。

#### 验收标准

1. WHEN Workbench 页面加载完成，THE System SHALL 从数据库查询当前 POS 对应的 VisionRecipe 并显示在页面上
2. THE System SHALL 显示配方名称、POS 值、左右泡棉 ROI 坐标和 Threshold_Config
3. WHEN User 切换 POS 选择，THE System SHALL 重新加载对应 POS 的 VisionRecipe 并更新显示
4. IF 当前 POS 没有对应的 VisionRecipe，THEN THE System SHALL 显示提示信息"当前 POS 无配方，请标定后保存"

### 需求 2: 检测自动使用配方参数

**用户故事:** 作为操作员，我希望检测时自动使用当前 POS 对应配方中的 ROI 和阈值，以便无需手动配置即可进行检测。

#### 验收标准

1. WHEN User 触发拍照检测或上传图片检测，THE System SHALL 使用当前 POS 对应的 VisionRecipe 中的 ROI 和 Threshold_Config
2. WHEN User 未手动标定 ROI，THE System SHALL 从 VisionRecipe 的 roi_config 字段读取 leftFoamROI 和 rightFoamROI
3. THE System SHALL 将 ROI 像素坐标转换为检测算法所需的比例坐标
4. THE System SHALL 使用 Threshold_Config 中的 minCoverage、minScore、maxOffsetX 和 maxOffsetY 作为检测阈值

### 需求 3: 标定 ROI 后选择保存目标

**用户故事:** 作为操作员，我希望在标定完 ROI 后选择保存到哪个 POS 的配方，以便灵活管理多个 POS 的配方。

#### 验收标准

1. WHEN User 完成拖拽框选 ROI 操作，THE System SHALL 显示"保存配方"按钮
2. WHEN User 点击"保存配方"按钮，THE System SHALL 弹出 POS 选择对话框，包含 POS 0、POS 1、POS 2 三个选项
3. WHEN User 选择一个 POS 并确认，THE System SHALL 将当前标定的 leftFoamROI 和 rightFoamROI 保存到对应 POS 的 VisionRecipe
4. THE System SHALL 仅更新选中 POS 的 VisionRecipe，不修改其他 POS 的配方
5. WHEN 保存成功，THE System SHALL 显示成功提示消息"配方已保存到 POS X"

### 需求 4: 临时切换配方进行检测

**用户故事:** 作为操作员，我希望临时切换使用其他配方进行检测，以便在不改变当前 POS 的情况下测试不同配方效果。

#### 验收标准

1. THE Workbench SHALL 显示"临时使用其他配方"按钮
2. WHEN User 点击"临时使用其他配方"按钮，THE System SHALL 显示所有可用配方列表，包含 POS、配方名称和 ROI 信息
3. WHEN User 选择一个配方，THE System SHALL 将该配方设置为临时配方用于下一次检测
4. THE System SHALL 在页面上显示"临时使用：POS X 配方"的提示信息
5. WHEN 检测完成后，THE System SHALL 保持临时配方状态直到 User 手动恢复或切换 POS
6. WHEN User 切换 POS 选择，THE System SHALL 清除临时配方状态并使用新 POS 对应的配方

### 需求 5: 配方 ROI 可视化

**用户故事:** 作为操作员，我希望在相机画面上看到当前配方的 ROI 框，以便直观了解检测区域位置。

#### 验收标准

1. WHEN Workbench 加载 VisionRecipe，THE System SHALL 在 Camera_Feed 上绘制左右泡棉 ROI 矩形框
2. THE System SHALL 使用不同颜色区分左泡棉 ROI（绿色）和右泡棉 ROI（蓝色）
3. THE System SHALL 在每个 ROI 框上标注文字标签"左泡棉"或"右泡棉"
4. WHEN User 切换 POS 或临时配方，THE System SHALL 清除旧的 ROI 框并绘制新配方的 ROI 框
5. WHEN Detection_Result 图像生成时，THE System SHALL 在结果图上绘制本次检测使用的 ROI 框

### 需求 6: 检测结果显示配方信息

**用户故事:** 作为操作员，我希望检测结果中显示本次使用的配方信息，以便追溯检测使用的参数。

#### 验收标准

1. WHEN 检测完成，THE System SHALL 在 Detection_Result 图像上叠加文字显示"使用配方: POS X"
2. THE System SHALL 在检测结果详情中显示配方名称、ROI 坐标和 Threshold_Config
3. THE System SHALL 记录本次检测使用的 VisionRecipe ID 到 FoamInspectionResult 的 result_data 字段
4. WHEN User 临时使用了其他配方，THE System SHALL 在结果中明确标注"临时使用: POS X 配方"

### 需求 7: 配方数据跨页面同步

**用户故事:** 作为操作员，我希望在配方管理页面编辑配方后，工作台能自动加载更新后的配方，以便确保数据一致性。

#### 验收标准

1. WHEN User 在 Recipe_Management_Page 保存配方修改，THE System SHALL 更新数据库中对应的 VisionRecipe 记录
2. WHEN User 从 Recipe_Management_Page 返回 Workbench，THE System SHALL 重新从数据库加载当前 POS 的 VisionRecipe
3. THE System SHALL 使用 VisionRecipe 的 updated_at 时间戳判断配方是否已更新
4. WHEN Workbench 检测到配方已更新，THE System SHALL 自动刷新 ROI 可视化显示

### 需求 8: 无配方时的向后兼容

**用户故事:** 作为操作员，我希望在没有配方的情况下仍能使用旧的手动标定逻辑，以便系统保持向后兼容。

#### 验收标准

1. WHEN 当前 POS 没有对应的 VisionRecipe，THE System SHALL 允许 User 手动拖拽框选 ROI
2. THE System SHALL 使用默认的 Threshold_Config（minCoverage=0.75, minScore=0.8, maxOffsetX=30, maxOffsetY=30）
3. WHEN User 未保存配方直接检测，THE System SHALL 使用手动标定的 ROI 和默认阈值进行检测
4. THE System SHALL 不强制要求 User 保存配方即可进行检测

### 需求 9: 配方保存的数据完整性

**用户故事:** 作为系统，我需要确保配方保存时包含所有必要数据，以便配方能被正确加载和使用。

#### 验收标准

1. WHEN System 保存 VisionRecipe，THE System SHALL 验证 leftFoamROI 和 rightFoamROI 包含 x、y、width、height 四个字段
2. THE System SHALL 验证 ROI 坐标值在图像尺寸范围内（x + width ≤ image_width, y + height ≤ image_height）
3. THE System SHALL 验证 Threshold_Config 包含 minCoverage、minScore、maxOffsetX、maxOffsetY 四个字段
4. THE System SHALL 验证阈值范围（0 ≤ minCoverage ≤ 1, 0 ≤ minScore ≤ 1, maxOffsetX ≥ 0, maxOffsetY ≥ 0）
5. IF 验证失败，THEN THE System SHALL 返回错误消息并拒绝保存

### 需求 10: 配方操作的用户界面友好性

**用户故事:** 作为操作员，我希望配方相关操作的界面清晰易用，以便快速完成配方管理任务。

#### 验收标准

1. THE Workbench SHALL 在顶部显示当前使用的配方信息卡片，包含 POS、配方名称和状态（正常/临时）
2. THE System SHALL 使用不同背景颜色区分正常配方（蓝色）和临时配方（橙色）
3. WHEN User 进行配方操作（保存、切换），THE System SHALL 显示加载指示器并在操作完成后显示结果提示
4. THE System SHALL 在 ROI 框绘制时使用半透明填充和清晰边框，确保不遮挡相机画面
5. THE Workbench SHALL 提供快速跳转到 Recipe_Management_Page 的链接按钮

### 需求 11: 配方数据的持久化存储

**用户故事:** 作为系统，我需要将配方数据持久化存储到数据库，以便配方在系统重启后仍然可用。

#### 验收标准

1. WHEN User 保存配方，THE System SHALL 调用 VisionRecipe.objects.update_or_create 方法更新或创建记录
2. THE System SHALL 使用 recipe_type='FOAM_2D', pos=X, camera_side='both' 作为唯一性约束条件
3. THE System SHALL 保存 roi_config 为 JSON 格式，包含 leftFoamROI 和 rightFoamROI 对象
4. THE System SHALL 保存 threshold_config 为 JSON 格式，包含阈值参数
5. THE System SHALL 自动更新 updated_at 时间戳

### 需求 12: 配方加载的性能优化

**用户故事:** 作为系统，我需要优化配方加载性能，以便工作台页面快速响应。

#### 验收标准

1. WHEN Workbench 加载时，THE System SHALL 使用单次数据库查询获取所有 FOAM_2D 类型的活动配方
2. THE System SHALL 在前端缓存配方数据，避免每次 POS 切换时重新查询数据库
3. THE System SHALL 仅在配方保存或页面刷新时重新加载配方数据
4. WHEN 加载配方列表时，THE System SHALL 在 500 毫秒内完成加载并渲染 ROI 可视化

