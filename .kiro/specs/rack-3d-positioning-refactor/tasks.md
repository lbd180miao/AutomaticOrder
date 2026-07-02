# 实施计划：3D深度相机料架定位系统

## 概述

本实施计划将3D深度相机料架定位功能的设计转化为可执行的开发任务。系统采用Django + Open3D + NumPy技术栈,使用Provider模式实现Mock/Real双模式,支持无硬件开发测试。实施遵循自底向上的顺序:首先实现数据模型和Provider接口层,然后是核心算法模块,再是服务协调层和API层,最后实现前端界面和集成测试。

## 实施进度（2026-07-02 更新）

`apps/vision/rack_3d/` 包已从 stub 落地为可运行实现，MOCK 端到端流程打通：

- ✅ Provider 层（`providers.py`）：Mock/Real 三类 Provider + ProviderFactory（任务 2.1/2.3/2.4/2.6/2.7）
- ✅ 点云处理（`processors.py`）：坐标转换 / ROI 裁剪 / 离群滤波 / 体素下采样（任务 3.1/3.3/3.5，Open3D 缺失时 NumPy 回退）
- ✅ 定位算法（`algorithms.py`）：Z=RANSAC 平面、Y=前边缘中位数、X=立柱中位数（任务 4.1/4.3/4.4）
- ✅ 补偿计算（`calculators.py`）：偏移/补偿/校验/综合置信度（任务 5.1/5.3）
- ✅ 主服务（`services.py`）：`execute_positioning` 全链路 + 结果落库（任务 7.1-7.5）
- ✅ 异常体系（`exceptions.py`）：错误码 + 异常类层次（任务 8.1/8.2）
- ✅ 配置：settings 增加 `RACK_3D_POSITIONING_MODE='MOCK'`（任务 12.1 部分）
- ✅ 测试：`rack_3d/tests/` 42 个用例全通过，含 MOCK 端到端集成测试（含 Property 2/3/5/8/10 内联断言）

- ✅ REST API（`api.py`/`urls.py`，任务 9）：capture / calculate / recipes / rois / results / coordinates，挂载 `/vision/rack-3d/`
- ✅ 前端 Canvas 双窗口（`templates/vision/rack_3d_positioning.html`，任务 11）：模式显示、配方/层号/ROI类型选择、点云 X-Y 投影渲染、拖拽画 ROI、采集/保存ROI/计算/计算并保存
- ✅ seed_rack_3d_demo 命令（`management/commands/seed_rack_3d_demo.py`，任务 12.2）：一键生成三层配方+ROI+历史结果
- ✅ 部署文档（`apps/vision/rack_3d/README.md`，任务 12.3）
- ✅ 属性测试（`tests/test_properties.py`）：Property 1/2/3/4/5/7/8/9 各随机迭代 50-100 次（不依赖 Hypothesis，用 NumPy RNG 循环）
- ✅ 测试：`rack_3d/tests/` **59 个用例全通过**（单元 + API + MOCK 端到端 + 属性）
- ✅ 运行态冒烟：`runserver` 后 `/vision/rack-3d/` 200，capture 返回 2040 点，calculate 成功、actual≈(900,530,1220)、confidence 0.906

**待办**：Real 模式现场联调（接真实相机/机器人服务）、性能基准（任务 13.2，可选）。若需严格 Hypothesis，可 `pip install hypothesis` 后将 test_properties 迁移为 `@given`。

## 任务

- [ ] 1. 搭建项目基础架构和数据模型
  - [x] 1.1 创建vision应用的rack_3d模块目录结构
    - 在`apps/vision/`下创建`rack_3d/`子包
    - 创建`__init__.py`, `providers.py`, `processors.py`, `algorithms.py`, `calculators.py`, `services.py`文件
    - 创建`tests/`测试目录,包含`test_providers.py`, `test_processors.py`, `test_algorithms.py`, `test_calculators.py`
    - _Requirements: 19.1, 19.2, 19.3_

  - [ ] 1.2 扩展RackLocationRecipe模型
    - 在现有RackLocationRecipe模型中验证并添加必要字段:`hand_eye_config`, `reference_feature_config`, `confidence_threshold`
    - 确保`standard_x`, `standard_y`, `standard_z`字段存在(DecimalField, max_digits=10, decimal_places=3)
    - 确保`max_offset_x`, `max_offset_y`, `max_offset_z`字段存在
    - 创建Django migration文件
    - _Requirements: 10.1, 10.2, 19.4, 19.5_

  - [ ] 1.3 扩展RackLocationROI3D模型
    - 验证或创建RackLocationROI3D模型,包含`recipe`, `roi_name`, `layer_no`外键/字段
    - 添加六个边界字段:`x_min`, `x_max`, `y_min`, `y_max`, `z_min`, `z_max`(DecimalField)
    - 添加CheckConstraint验证min < max约束
    - 创建Django migration文件
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ] 1.4 扩展RackLocationResult模型
    - 验证或扩展RackLocationResult模型,包含`vision_task`, `recipe`外键
    - 添加字段:`position_no`, `layer_no`, `actual_x`, `actual_y`, `actual_z`
    - 添加字段:`offset_x`, `offset_y`, `offset_z`, `confidence`, `is_success`
    - 添加字段:`raw_data_path`, `result_image_path`, `result_data`(JSONField), `error_code`, `error_message`
    - 创建Django migration文件
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 9.5_

  - [ ] 1.5 运行数据库迁移并验证
    - 执行`python manage.py makemigrations`
    - 执行`python manage.py migrate`
    - 在Django shell中测试模型创建和约束验证
    - _Requirements: 19.6_


- [ ] 2. 实现Provider设计模式接口和实现类
  - [ ] 2.1 实现HandEyeProvider接口和实现类
    - 在`providers.py`中定义HandEyeProvider抽象基类,包含`get_hand_eye_matrix()`和`save_hand_eye_matrix()`方法
    - 实现MockHandEyeProvider,返回预设的4x4手眼标定矩阵(相机相对法兰:前120mm,下60mm,右30mm)
    - 实现RealHandEyeProvider,从RackLocationRecipe的hand_eye_config字段读取T_flange_camera矩阵
    - _Requirements: 14.1, 14.2, 14.3, 15.1, 15.2, 15.3, 15.4, 15.5, 2.4_

  - [ ]* 2.2 编写HandEyeProvider属性测试
    - **Property 7: 手眼矩阵不变性**
    - **Validates: Requirements 2.4**
    - 使用Hypothesis测试多次获取同一配方的手眼矩阵应返回相同值
    - 测试MockHandEyeProvider的矩阵固定不变性
    - _Requirements: 2.4_

  - [ ] 2.3 实现RobotPoseProvider接口和实现类
    - 定义RobotPoseProvider抽象基类,包含`get_robot_pose_matrix()`和`get_robot_pose_dict()`方法
    - 实现MockRobotPoseProvider,提供三层预设拍照位姿(Layer 1: Z=600, Layer 2: Z=900, Layer 3: Z=1200)
    - 实现RealRobotPoseProvider,从机器人控制器读取实时位姿并计算变换矩阵(使用scipy.spatial.transform.Rotation)
    - _Requirements: 14.4, 14.5, 14.6, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7_

  - [ ] 2.4 实现DepthCameraProvider接口和实现类
    - 定义DepthCameraProvider抽象基类,包含`capture_pointcloud()`方法
    - 实现MockDepthCameraProvider,生成包含支撑面+立柱+边缘+噪声的模拟点云(H×W×3格式)
    - 实现RealDepthCameraProvider,调用dm_camera模块的capture_frame_data方法采集真实点云
    - _Requirements: 14.7, 14.8, 14.9, 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 1.1, 1.2_

  - [ ]* 2.5 编写DepthCameraProvider属性测试
    - **Property 10: 数据结构完整性**
    - **Validates: Requirements 1.2**
    - 使用Hypothesis测试capture_pointcloud返回值包含所有必需字段(data, width, height, frame_index, confidence)
    - 验证data字段是numpy array且shape正确
    - _Requirements: 1.2_

  - [ ] 2.6 实现ProviderFactory工厂类
    - 实现create_hand_eye_provider()方法,根据mode参数返回Mock或Real实现
    - 实现create_robot_pose_provider()方法,根据mode参数返回Mock或Real实现
    - 实现create_depth_camera_provider()方法,根据mode参数返回Mock或Real实现
    - 从Django settings读取RACK_3D_POSITIONING_MODE配置
    - _Requirements: 14.10, 14.11, 18.1, 18.2, 18.3, 18.4_

  - [ ]* 2.7 编写Provider单元测试
    - 测试MockHandEyeProvider返回固定矩阵
    - 测试MockRobotPoseProvider三层位姿正确
    - 测试MockDepthCameraProvider生成点云格式正确
    - 测试ProviderFactory根据mode正确创建实例
    - 测试错误处理:缺失配置、无效参数等
    - _Requirements: 26.1, 26.2_


- [ ] 3. 实现点云处理模块PointCloudProcessor
  - [ ] 3.1 实现坐标转换方法transform_to_robot_coords()
    - 在`processors.py`中创建PointCloudProcessor类
    - 实现transform_to_robot_coords()方法:接收点云(N×3或H×W×3)、T_flange_camera、T_base_flange
    - 将点云展平为N×3,过滤无效点(NaN、零值)
    - 应用链式变换:P_base = T_base_flange @ T_flange_camera @ P_camera
    - 返回机器人坐标系点云(N×3)
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 4.5, 4.6, 21.1, 21.2, 21.5, 21.6, 21.7_

  - [ ]* 3.2 编写坐标转换属性测试
    - **Property 1: 坐标转换保持可逆性**
    - **Validates: Requirements 2.1, 2.2, 2.3**
    - 使用Hypothesis生成随机点云、T矩阵,验证正向变换后逆变换可恢复原始坐标
    - **Property 2: 坐标转换保持向量关系**
    - **Validates: Requirements 2.1**
    - 验证两点间欧氏距离在坐标转换后保持不变(刚体变换)
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ] 3.3 实现ROI裁剪方法crop_roi()
    - 实现crop_roi()方法:接收点云(N×3)和roi_bounds字典(x_min, x_max, y_min, y_max, z_min, z_max)
    - 应用六个边界条件过滤点云
    - 返回裁剪后的点云和有效点计数
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.7_

  - [ ]* 3.4 编写ROI裁剪属性测试
    - **Property 3: ROI裁剪正确性**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
    - 使用Hypothesis生成随机点云和ROI边界,验证裁剪后所有点在边界内
    - **Property 6: ROI边界有效性**
    - **Validates: Requirements 3.4**
    - 验证系统拒绝min >= max的无效边界
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 3.4_

  - [ ] 3.5 实现点云滤波和下采样方法
    - 实现filter_outliers()方法:使用Open3D的remove_statistical_outlier进行离群点滤波
    - 实现downsample()方法:使用Open3D的voxel_down_sample进行体素下采样
    - 添加辅助方法将numpy array转换为Open3D PointCloud对象
    - _Requirements: 25.2, 25.4, 25.5_

  - [ ]* 3.6 编写点云处理属性测试
    - **Property 4: 无效点过滤完整性**
    - **Validates: Requirements 4.5, 4.6**
    - 使用Hypothesis生成包含NaN、inf、零值的点云,验证过滤后不含无效值
    - **Property 9: 点云下采样保持空间分布**
    - **Validates: Requirements 21.1, 21.2**
    - 验证下采样后点云边界框与原始边界框差异< 5%
    - _Requirements: 4.5, 4.6, 21.1, 21.2_

  - [ ]* 3.7 编写PointCloudProcessor单元测试
    - 测试空点云处理
    - 测试单点点云处理
    - 测试全部点在ROI外的情况
    - 测试组织化(H×W×3)和非组织化(N×3)点云格式兼容性
    - _Requirements: 26.3, 21.1, 21.2_


- [ ] 4. 实现定位算法模块PositioningAlgorithm
  - [ ] 4.1 实现Z轴定位方法detect_z_axis()
    - 在`algorithms.py`中创建PositioningAlgorithm类
    - 实现detect_z_axis()方法:接收支撑面ROI点云
    - 使用Open3D的segment_plane进行RANSAC平面拟合
    - 计算平面方程[a,b,c,d]和内点集
    - 计算内点Z坐标的平均值作为实际Z坐标
    - 返回字典:{z_actual, plane_model, inlier_count, confidence}
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 25.3_

  - [ ]* 4.2 编写Z轴定位属性测试
    - **Property 8: 平面拟合有效性**
    - **Validates: Requirements 5.1, 5.2**
    - 使用Hypothesis生成包含至少10个共面点(带小幅噪声)的点云
    - 验证RANSAC成功返回平面方程且内点比例> 0.5
    - 验证拟合平面高度与真实值差异在合理范围内
    - _Requirements: 5.1, 5.2_

  - [ ] 4.3 实现Y轴定位方法detect_y_axis()
    - 实现detect_y_axis()方法:接收前边缘ROI点云
    - 计算Y坐标的中位数作为实际Y坐标
    - 基于Y坐标标准差计算置信度(标准差越小置信度越高)
    - 返回字典:{y_actual, edge_points_count, confidence}
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 4.4 实现X轴定位方法detect_x_axis()
    - 实现detect_x_axis()方法:接收立柱ROI点云
    - 计算X坐标的中位数作为实际X坐标
    - 基于X坐标标准差计算置信度
    - 返回字典:{x_actual, pillar_points_count, confidence}
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 4.5 编写定位算法单元测试
    - 测试detect_z_axis对理想平面和噪声平面的处理
    - 测试detect_y_axis边缘检测的鲁棒性
    - 测试detect_x_axis立柱检测的鲁棒性
    - 测试点数不足时的错误处理
    - 测试置信度计算的合理性
    - _Requirements: 26.3_

- [ ] 5. 实现补偿计算模块CompensationCalculator
  - [ ] 5.1 实现补偿值计算方法calculate_offsets()
    - 在`calculators.py`中创建CompensationCalculator类
    - 实现calculate_offsets()方法:接收actual_x/y/z和standard_x/y/z
    - 计算offset_x = actual_x - standard_x
    - 计算offset_y = actual_y - standard_y
    - 计算offset_z = actual_z - standard_z
    - 返回字典:{offset_x, offset_y, offset_z}
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 5.2 编写补偿值计算属性测试
    - **Property 5: 补偿值计算正确性**
    - **Validates: Requirements 9.2, 9.3, 9.4**
    - 使用Hypothesis生成随机actual和standard坐标
    - 验证offset = actual - standard公式正确性
    - 验证精度保持到0.001毫米
    - _Requirements: 9.2, 9.3, 9.4_

  - [ ] 5.3 实现补偿值验证方法validate_offsets()
    - 实现validate_offsets()方法:接收offset_x/y/z和max_offset_x/y/z
    - 检查abs(offset_x) <= max_offset_x
    - 检查abs(offset_y) <= max_offset_y
    - 检查abs(offset_z) <= max_offset_z
    - 返回bool表示是否在允许范围内
    - _Requirements: 9.6_

  - [ ]* 5.4 编写CompensationCalculator单元测试
    - 测试正负补偿值计算
    - 测试补偿值超限检测
    - 测试边界值处理
    - _Requirements: 26.3_


- [ ] 6. Checkpoint - 确保核心模块测试通过
  - 运行所有属性测试:`pytest -v apps/vision/rack_3d/tests/ -k property`
  - 运行所有单元测试:`pytest -v apps/vision/rack_3d/tests/`
  - 确保测试覆盖率≥85%
  - 如有问题向用户反馈

- [ ] 7. 实现主服务协调器RackPositioningService
  - [ ] 7.1 实现RackPositioningService初始化和Provider注入
    - 在`services.py`中创建RackPositioningService类
    - 实现__init__方法:接收mode参数('MOCK'或'REAL')
    - 使用ProviderFactory创建hand_eye_provider、robot_pose_provider、depth_camera_provider实例
    - 实例化PointCloudProcessor、PositioningAlgorithm、CompensationCalculator
    - _Requirements: 14.10, 14.11_

  - [ ] 7.2 实现主定位流程execute_positioning()
    - 实现execute_positioning()方法:接收recipe_id和layer_no
    - Step 1: 加载RackLocationRecipe配方
    - Step 2: 调用depth_camera_provider.capture_pointcloud()采集点云
    - Step 3: 获取hand_eye_provider.get_hand_eye_matrix()和robot_pose_provider.get_robot_pose_matrix()
    - Step 4: 调用processor.transform_to_robot_coords()转换坐标
    - Step 5: 调用_load_rois()加载ROI配置
    - Step 6: 调用_crop_all_rois()裁剪三个ROI(support, edge, pillar)
    - _Requirements: 1.1, 2.1, 2.2, 2.3_

  - [ ] 7.3 实现定位计算和结果保存逻辑
    - Step 7: 调用algorithm.detect_z_axis(roi_crops['support'])
    - Step 8: 调用algorithm.detect_y_axis(roi_crops['edge'])
    - Step 9: 调用algorithm.detect_x_axis(roi_crops['pillar'])
    - Step 10: 调用calculator.calculate_offsets()计算补偿值
    - Step 11: 调用calculator.validate_offsets()验证补偿范围
    - Step 12: 计算综合置信度(取三轴检测置信度的最小值)
    - Step 13: 调用_save_result()保存到RackLocationResult
    - 返回完整结果字典
    - _Requirements: 5.1, 6.1, 7.1, 9.1, 9.6, 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ] 7.4 实现辅助方法_load_rois()和_crop_all_rois()
    - 实现_load_rois():从RackLocationROI3D查询当前层的ROI配置(support, edge, pillar)
    - 实现_crop_all_rois():对每个ROI调用processor.crop_roi()
    - 对每个ROI可选地执行滤波和下采样(点数>1000时)
    - _Requirements: 3.5, 4.1, 4.2, 4.3, 4.4_

  - [ ] 7.5 实现结果保存方法_save_result()
    - 创建VisionTask记录(task_type='RACK_3D_POSITIONING')
    - 创建RackLocationResult记录,填充所有字段
    - 保存算法详情到result_data JSONField
    - 返回结果字典
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 24.1, 24.2, 24.3, 24.4, 24.5, 24.6, 24.7_

  - [ ]* 7.6 编写RackPositioningService集成测试
    - 测试Mock模式下完整定位流程
    - 测试点云采集失败的错误处理
    - 测试ROI点数不足的错误处理
    - 测试补偿值超限的处理
    - 测试结果保存的完整性
    - _Requirements: 26.4_


- [ ] 8. 实现错误处理和异常体系
  - [ ] 8.1 定义错误码常量类RackPositioningErrorCode
    - 在`exceptions.py`中定义RackPositioningErrorCode类
    - 定义点云采集错误码(E1001-E1004)
    - 定义坐标转换错误码(E2001-E2004)
    - 定义ROI错误码(E3001-E3003)
    - 定义定位算法错误码(E4001-E4005)
    - 定义补偿计算错误码(E5001-E5002)
    - 定义PLC通讯错误码(E6001-E6002)
    - _Requirements: 22.2, 22.3, 22.4, 22.5, 22.6_

  - [ ] 8.2 定义异常类层次结构
    - 定义RackPositioningException基类,包含error_code, message, details属性
    - 定义PointCloudError、CoordinateTransformError、ROIError、PositioningAlgorithmError子类
    - 在各模块中使用异常类代替普通错误返回
    - _Requirements: 22.1, 22.7, 22.8_

  - [ ] 8.3 实现错误日志记录
    - 配置Python logging,设置格式化器和文件handler
    - 在关键操作点添加日志记录(INFO级别)
    - 在异常捕获处添加错误日志(ERROR级别,包含堆栈)
    - _Requirements: 24.1, 22.8_

  - [ ]* 8.4 编写错误处理单元测试
    - 测试异常类的error_code和message正确性
    - 测试各模块抛出正确的异常类型
    - 测试错误日志记录完整性
    - _Requirements: 26.3_

- [ ] 9. 实现Django REST API接口
  - [ ] 9.1 创建Serializer类
    - 在`serializers.py`中创建RackLocationRecipeSerializer
    - 创建RackLocationROI3DSerializer
    - 创建RackLocationResultSerializer
    - 创建定位请求和响应的自定义Serializer
    - _Requirements: 20.8_

  - [ ] 9.2 实现采集点云接口POST /api/vision/rack-3d/capture
    - 在`views.py`中创建RackPositioningViewSet
    - 实现capture动作:接收recipe_id和layer_no
    - 调用depth_camera_provider.capture_pointcloud()
    - 返回点云元数据(frame_index, width, height, point_count, paths)
    - _Requirements: 20.1, 1.1, 1.2, 1.3_

  - [ ] 9.3 实现定位计算接口POST /api/vision/rack-3d/calculate
    - 实现calculate动作:接收recipe_id和layer_no
    - 调用RackPositioningService.execute_positioning()
    - 返回完整定位结果(实际坐标、补偿值、置信度、算法详情)
    - 捕获异常并返回错误响应(HTTP 400/500)
    - _Requirements: 20.2, 20.8, 20.9_

  - [ ] 9.4 实现配方和ROI管理接口
    - 实现GET /api/vision/rack-3d/recipes获取配方列表
    - 实现GET /api/vision/rack-3d/recipes/{id}/rois获取ROI配置(支持layer_no查询参数)
    - 实现POST /api/vision/rack-3d/rois创建或更新ROI
    - 验证ROI边界:min < max,否则返回HTTP 400
    - _Requirements: 20.3, 20.4, 20.5, 3.4_

  - [ ] 9.5 实现历史结果查询和坐标更新接口
    - 实现GET /api/vision/rack-3d/results查询历史结果(支持position_no, layer_no, limit查询参数)
    - 实现PATCH /api/vision/rack-3d/recipes/{id}/coordinates更新理论坐标
    - 验证坐标值格式和精度
    - _Requirements: 20.6, 20.7, 10.3, 10.4, 10.5, 10.6, 8.6_

  - [ ] 9.6 配置URL路由
    - 在`urls.py`中注册RackPositioningViewSet到router
    - 配置路径前缀`/api/vision/rack-3d/`
    - 在主urls.py中包含rack_3d的urls
    - _Requirements: 20.1-20.7_

  - [ ]* 9.7 编写REST API端到端测试
    - 使用Django TestCase或pytest-django测试所有API接口
    - 测试正常流程:采集->计算->查询结果
    - 测试错误处理:无效recipe_id、层号超范围、ROI边界非法
    - 测试分页和过滤功能
    - _Requirements: 26.4_


- [ ] 10. Checkpoint - 确保后端服务和API正常工作
  - 启动Django开发服务器:`python manage.py runserver`
  - 使用Postman或curl测试所有API接口
  - 验证Mock模式下可以成功完成定位计算
  - 检查日志输出是否正确
  - 如有问题向用户反馈

- [ ] 11. 实现前端Canvas点云可视化
  - [ ] 11.1 创建Django模板和静态资源
    - 创建`templates/vision/rack_3d_positioning.html`模板
    - 创建`static/js/rack_3d_canvas.js`处理Canvas渲染
    - 创建`static/css/rack_3d.css`定义样式
    - 实现左右双窗口布局(左侧ROI绘制,右侧结果预览)
    - _Requirements: 11.1, 11.2_

  - [ ] 11.2 实现点云投影和Canvas渲染
    - 在rack_3d_canvas.js中实现点云3D->2D投影(XY平面或正交投影)
    - 实现Canvas绘制点云:遍历点数组,绘制像素点,按深度着色
    - 实现Canvas缩放和平移交互(鼠标滚轮缩放,拖拽平移)
    - 实现坐标轴和刻度显示
    - _Requirements: 11.3, 11.4_

  - [ ] 11.3 实现ROI绘制和编辑功能
    - 实现鼠标拖拽绘制矩形ROI框
    - 实时显示ROI框的坐标值(x_min, x_max, y_min, y_max)
    - 实现ROI框的选择、移动、缩放功能
    - 支持多个ROI框的显示和管理(不同颜色区分类型)
    - _Requirements: 11.3, 11.4, 11.7_

  - [ ] 11.4 实现前端控制面板和参数输入
    - 实现层号选择器(1/2/3按钮)
    - 实现ROI类型下拉选择(main, support, edge, pillar)
    - 实现六个边界输入框(X Min/Max, Y Min/Max, Z Min/Max)
    - 输入框与Canvas ROI框双向绑定:修改输入框更新Canvas,拖拽Canvas更新输入框
    - _Requirements: 11.5, 11.6, 13.1, 13.2_

  - [ ] 11.5 实现前端操作按钮
    - 实现"采集点云"按钮:调用POST /api/vision/rack-3d/capture,显示点云预览
    - 实现"自动填充ROI"按钮:根据点云边界框自动计算ROI范围
    - 实现"预览裁剪"按钮:调用后端裁剪接口,右侧窗口显示裁剪结果
    - 实现"保存ROI"按钮:调用POST /api/vision/rack-3d/rois保存配置
    - 实现"复制上一层"按钮:复制layer_no-1的ROI配置到当前层
    - 实现"重置"按钮:清空当前ROI配置
    - _Requirements: 13.3, 11.8, 11.9, 13.4, 13.5, 13.6_

  - [ ] 11.6 实现右侧结果预览窗口
    - 显示裁剪后的点云(Canvas渲染)
    - 显示实际坐标(actual_x, actual_y, actual_z)
    - 显示补偿值(offset_x, offset_y, offset_z)和状态指示(正常/超限)
    - 显示置信度百分比和等级(优秀/良好/较低)
    - 显示有效点数量
    - 定位成功绿色显示,失败红色显示并显示错误信息
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [ ] 11.7 实现模式显示和配方选择
    - 页面顶部显示当前运行模式(MOCK调试模式 / REAL生产模式)
    - 实现配方下拉选择器:从GET /api/vision/rack-3d/recipes获取列表
    - 配方切换时自动加载对应的理论坐标和ROI配置
    - _Requirements: 18.5_

  - [ ]* 11.8 前端手动测试
    - 测试点云渲染性能(10万点以上)
    - 测试ROI绘制和拖拽的流畅性
    - 测试参数输入验证
    - 测试所有按钮功能
    - 测试响应式布局


- [ ] 12. 配置管理和Demo数据准备
  - [ ] 12.1 配置Django settings
    - 在settings.py中添加RACK_3D_POSITIONING_MODE配置项(默认'MOCK')
    - 配置日志系统:文件handler按天轮转,保留30天
    - 配置MEDIA_ROOT和MEDIA_URL用于保存点云文件
    - 添加Open3D、NumPy、SciPy、Hypothesis到requirements.txt
    - _Requirements: 18.1, 18.2, 18.6_

  - [ ] 12.2 创建Demo数据初始化命令seed_rack_3d_demo
    - 在`management/commands/`中创建seed_rack_3d_demo.py
    - 创建示例配方:recipe_name="Demo料架A-位置1",设置理论坐标
    - 创建三层的ROI配置(每层3个ROI:support, edge, pillar)
    - 创建模拟手眼标定矩阵并保存到hand_eye_config
    - 创建几条历史定位结果示例
    - _Requirements: 26.4_

  - [ ] 12.3 编写部署文档README_RACK_3D.md
    - 说明Mock模式和Real模式的区别
    - 提供开发环境搭建步骤(依赖安装、数据库迁移、Demo数据加载)
    - 提供API使用示例(curl命令)
    - 说明如何切换到Real模式并配置真实设备
    - 说明性能优化建议
    - _Requirements: 18.1-18.6_

- [ ] 13. 集成测试和性能验证
  - [ ]* 13.1 编写Mock模式端到端集成测试
    - 测试完整流程:创建配方->配置ROI->采集点云->执行定位->验证结果
    - 测试多层定位流程
    - 测试错误恢复:点云采集失败、RANSAC失败、补偿超限
    - 使用Django TestCase和pytest-django
    - _Requirements: 26.4_

  - [ ]* 13.2 性能基准测试
    - 测试640×480点云定位计算耗时(目标<2秒)
    - 测试1280×720点云定位计算耗时(目标<5秒)
    - 测试并发处理3层定位的性能
    - 测试前端Canvas渲染10万点点云的性能(目标<500ms)
    - 记录性能基准数据
    - _Requirements: 23.1, 23.2, 23.3, 23.4_

  - [ ]* 13.3 代码覆盖率检查
    - 运行`pytest --cov=apps/vision/rack_3d`生成覆盖率报告
    - 核心算法模块(processors, algorithms, calculators)覆盖率≥90%
    - Provider实现覆盖率≥80%
    - Service层覆盖率≥85%
    - 整体覆盖率≥75%
    - 如未达标,补充测试用例
    - _Requirements: 26.6_

- [ ] 14. 最终验收和交付
  - [ ] 14.1 完整功能演示
    - 启动Django服务(Mock模式)
    - 访问前端页面,演示ROI配置和点云可视化
    - 调用API执行定位计算,查看结果
    - 演示错误处理:无效参数、补偿超限等
    - 向用户确认功能符合预期

  - [ ] 14.2 代码审查和文档整理
    - 检查代码符合PEP8规范
    - 确保所有模块有docstring文档
    - 确保所有属性测试有正确的标签和注释
    - 整理README_RACK_3D.md部署文档
    - 整理API文档(可选:使用drf-yasg生成Swagger文档)

  - [ ] 14.3 交付清单检查
    - ✓ 数据模型扩展完成并迁移
    - ✓ Provider模式实现(Mock/Real双模式)
    - ✓ 点云处理模块(坐标转换、ROI裁剪、滤波)
    - ✓ 定位算法模块(Z/Y/X三轴检测)
    - ✓ 补偿计算模块
    - ✓ 主服务协调器
    - ✓ REST API接口(7个核心接口)
    - ✓ 前端Canvas界面(左右双窗口)
    - ✓ 10个属性测试
    - ✓ 单元测试和集成测试
    - ✓ 错误处理和日志记录
    - ✓ Demo数据和配置
    - ✓ 部署文档


## 注释

- 任务标记`*`表示可选任务(主要是测试相关),可根据时间和优先级跳过,但建议完成以保证质量
- 每个任务都关联了具体的需求条款(_Requirements: X.Y_),确保需求覆盖完整
- 属性测试任务明确标注了属性编号和验证的需求
- Checkpoint任务用于阶段性验收,确保增量开发质量
- 所有代码使用Python编写,基于Django 4.x + Open3D + NumPy技术栈
- Mock模式下无需真实硬件即可完成所有开发和测试工作
- Real模式实现为后续工厂集成预留接口

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": 0,
      "tasks": ["1.1"]
    },
    {
      "id": 1,
      "tasks": ["1.2", "1.3", "1.4"]
    },
    {
      "id": 2,
      "tasks": ["1.5", "2.1", "2.3", "2.4", "2.6"]
    },
    {
      "id": 3,
      "tasks": ["2.2", "2.5", "2.7", "3.1"]
    },
    {
      "id": 4,
      "tasks": ["3.2", "3.3", "3.5"]
    },
    {
      "id": 5,
      "tasks": ["3.4", "3.6", "3.7", "4.1"]
    },
    {
      "id": 6,
      "tasks": ["4.2", "4.3", "4.4", "5.1"]
    },
    {
      "id": 7,
      "tasks": ["4.5", "5.2", "5.3"]
    },
    {
      "id": 8,
      "tasks": ["5.4", "7.1"]
    },
    {
      "id": 9,
      "tasks": ["7.2", "7.4", "8.1", "8.2"]
    },
    {
      "id": 10,
      "tasks": ["7.3", "7.5", "8.3"]
    },
    {
      "id": 11,
      "tasks": ["7.6", "8.4", "9.1"]
    },
    {
      "id": 12,
      "tasks": ["9.2", "9.3", "9.4", "9.5", "9.6"]
    },
    {
      "id": 13,
      "tasks": ["9.7", "11.1", "11.2"]
    },
    {
      "id": 14,
      "tasks": ["11.3", "11.4", "11.7"]
    },
    {
      "id": 15,
      "tasks": ["11.5", "11.6"]
    },
    {
      "id": 16,
      "tasks": ["11.8", "12.1", "12.2"]
    },
    {
      "id": 17,
      "tasks": ["12.3", "13.1", "13.2", "13.3"]
    },
    {
      "id": 18,
      "tasks": ["14.1", "14.2", "14.3"]
    }
  ]
}
```
