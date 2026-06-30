# 需求文档：3D深度相机料架定位功能重构

## 简介

本项目旨在重构和优化AutomaticOrder Django项目中的3D深度相机料架定位功能。该系统用于工业自动化场景，通过3D点云采集和手眼标定，实现机器人对三层料架的精确装箱操作。

核心业务流程：料架到位后，3D相机为每层拍摄点云，通过手眼标定将相机坐标转换到机器人基坐标系，在机器人坐标系下裁剪每层的ROI区域，提取刚性基准（支撑面、前边缘、立柱）计算X/Y/Z三轴补偿值，最终将补偿值写入PLC供机器人使用。

## 术语表

- **System**: 3D深度相机料架定位系统
- **Point_Cloud_Acquisition_Module**: 点云采集模块
- **Hand_Eye_Calibration_Module**: 手眼标定模块
- **ROI_Recipe_Module**: 3D ROI配方模块
- **Positioning_Algorithm_Module**: 料架定位算法模块
- **Actual_Value_Calculation_Module**: 真实值计算模块
- **Compensation_Calculation_Module**: 补偿值计算模块
- **Frontend_Module**: 前端交互模块
- **Coordinate_Config_Module**: 坐标配置模块
- **Camera_Coordinate_System**: 相机坐标系
- **Robot_Base_Coordinate_System**: 机器人基坐标系
- **T_base_flange**: 机器人基座到法兰的变换矩阵
- **T_flange_camera**: 法兰到相机的变换矩阵（手眼标定矩阵）
- **P_camera**: 相机坐标系下的点云点
- **P_base**: 机器人基坐标系下的点云点
- **ROI**: Region of Interest，感兴趣区域
- **RANSAC**: Random Sample Consensus，随机抽样一致性算法
- **PLC**: Programmable Logic Controller，可编程逻辑控制器
- **Mock_Mode**: 模拟模式，使用模拟数据进行开发
- **Real_Mode**: 真实模式，使用真实设备数据
- **Provider**: 提供者接口，用于抽象数据来源

## 需求

### 需求1：点云采集

**用户故事**：作为系统操作员，我希望系统能够调用3D相机SDK采集点云数据，以便获取料架的三维信息。

#### 验收标准

1. WHEN 用户请求采集点云，THE Point_Cloud_Acquisition_Module SHALL 调用3D相机SDK获取点云数据
2. THE Point_Cloud_Acquisition_Module SHALL 返回包含宽度、高度和三维坐标数组的点云数据结构
3. WHEN 采集失败，THE Point_Cloud_Acquisition_Module SHALL 返回描述性错误信息
4. WHERE Mock_Mode 启用，THE Point_Cloud_Acquisition_Module SHALL 使用模拟点云数据代替真实相机采集
5. WHERE Real_Mode 启用，THE Point_Cloud_Acquisition_Module SHALL 连接物理3D相机设备并采集真实点云

### 需求2：手眼标定坐标转换

**用户故事**：作为系统开发者，我希望实现相机坐标到机器人坐标的转换，以便在统一坐标系下处理点云数据。

#### 验收标准

1. THE Hand_Eye_Calibration_Module SHALL 实现坐标转换公式 P_base = T_base_flange × T_flange_camera × P_camera
2. WHEN 接收到 P_camera 点云数据，THE Hand_Eye_Calibration_Module SHALL 应用 T_flange_camera 转换到法兰坐标系
3. WHEN 接收到法兰坐标系点云，THE Hand_Eye_Calibration_Module SHALL 应用 T_base_flange 转换到机器人基坐标系
4. THE Hand_Eye_Calibration_Module SHALL 保持 T_flange_camera 在标定完成后固定不变
5. WHEN 机器人移动到新位置，THE Hand_Eye_Calibration_Module SHALL 使用更新后的 T_base_flange 矩阵
6. WHERE Mock_Mode 启用，THE Hand_Eye_Calibration_Module SHALL 使用预设的模拟手眼标定矩阵

### 需求3：3D ROI配方管理

**用户故事**：作为配方工程师，我希望为每层料架配置多类型ROI区域，以便精确提取定位基准。

#### 验收标准

1. THE ROI_Recipe_Module SHALL 存储每层料架的主ROI、支撑面ROI、前边缘ROI和立柱ROI配置
2. THE ROI_Recipe_Module SHALL 使用机器人基坐标系存储所有ROI坐标
3. THE ROI_Recipe_Module SHALL 为每个ROI存储x_min、x_max、y_min、y_max、z_min和z_max六个边界值
4. WHEN 用户创建ROI配置，THE ROI_Recipe_Module SHALL 验证最小值小于对应的最大值
5. THE ROI_Recipe_Module SHALL 支持按层号和ROI类型检索配置
6. THE ROI_Recipe_Module SHALL 关联到料架定位配方记录

### 需求4：点云ROI裁剪

**用户故事**：作为系统开发者，我希望在机器人坐标系下裁剪点云ROI，以便只处理目标区域的数据。

#### 验收标准

1. WHEN 接收到机器人坐标系点云 P_base，THE System SHALL 应用ROI边界条件裁剪点云
2. THE System SHALL 保留满足 roi_x_min <= X_base <= roi_x_max 条件的点
3. THE System SHALL 保留满足 roi_y_min <= Y_base <= roi_y_max 条件的点
4. THE System SHALL 保留满足 roi_z_min <= Z_base <= roi_z_max 条件的点
5. THE System SHALL 过滤掉深度值为零或无效的点
6. THE System SHALL 过滤掉坐标值超过物理合理范围的点
7. WHEN ROI内有效点数少于最小阈值，THE System SHALL 返回错误信息

### 需求5：Z轴定位（支撑面检测）

**用户故事**：作为定位算法开发者，我希望通过RANSAC平面拟合提取支撑面高度，以便计算Z轴补偿值。

#### 验收标准

1. WHEN 接收到支撑面ROI点云，THE Positioning_Algorithm_Module SHALL 使用RANSAC算法拟合平面
2. THE Positioning_Algorithm_Module SHALL 计算拟合平面的平均高度作为实际Z坐标
3. THE Positioning_Algorithm_Module SHALL 过滤离群点后再进行平面拟合
4. THE Positioning_Algorithm_Module SHALL 返回Z轴实际值，精度为0.001毫米
5. WHEN 平面拟合质量低于阈值，THE Positioning_Algorithm_Module SHALL 标记置信度为低

### 需求6：Y轴定位（前边缘检测）

**用户故事**：作为定位算法开发者，我希望检测料架前边缘位置，以便计算Y轴补偿值。

#### 验收标准

1. WHEN 接收到前边缘ROI点云，THE Positioning_Algorithm_Module SHALL 提取边缘线特征
2. THE Positioning_Algorithm_Module SHALL 计算边缘线的Y坐标中位数作为实际Y坐标
3. THE Positioning_Algorithm_Module SHALL 返回Y轴实际值，精度为0.001毫米
4. WHEN 边缘检测置信度低于阈值，THE Positioning_Algorithm_Module SHALL 标记置信度为低

### 需求7：X轴定位（立柱检测）

**用户故事**：作为定位算法开发者，我希望检测料架立柱或侧边位置，以便计算X轴补偿值。

#### 验收标准

1. WHEN 接收到立柱ROI点云，THE Positioning_Algorithm_Module SHALL 提取立柱或侧边特征
2. THE Positioning_Algorithm_Module SHALL 计算立柱X坐标中位数作为实际X坐标
3. THE Positioning_Algorithm_Module SHALL 返回X轴实际值，精度为0.001毫米
4. WHEN 立柱检测置信度低于阈值，THE Positioning_Algorithm_Module SHALL 标记置信度为低

### 需求8：真实值计算与历史记录

**用户故事**：作为质量工程师，我希望系统计算并保留每层的真实X/Y/Z位置历史记录，以便追溯和分析。

#### 验收标准

1. WHEN 完成三轴定位计算，THE Actual_Value_Calculation_Module SHALL 计算当前层的实际X、Y、Z坐标
2. THE Actual_Value_Calculation_Module SHALL 保存每次计算的真实值到数据库
3. THE Actual_Value_Calculation_Module SHALL 记录计算时间戳
4. THE Actual_Value_Calculation_Module SHALL 关联料架ID和层号
5. THE Actual_Value_Calculation_Module SHALL 记录置信度值
6. THE Actual_Value_Calculation_Module SHALL 保留至少最近100次历史记录

### 需求9：补偿值计算

**用户故事**：作为系统操作员，我希望系统计算理论值与真实值的差异，以便生成机器人补偿量。

#### 验收标准

1. WHEN 获得真实X/Y/Z坐标，THE Compensation_Calculation_Module SHALL 读取配方中的理论坐标值
2. THE Compensation_Calculation_Module SHALL 计算 offset_x = actual_x - standard_x
3. THE Compensation_Calculation_Module SHALL 计算 offset_y = actual_y - standard_y
4. THE Compensation_Calculation_Module SHALL 计算 offset_z = actual_z - standard_z
5. THE Compensation_Calculation_Module SHALL 返回三轴补偿值，精度为0.001毫米
6. WHEN 补偿值超出配方允许范围，THE Compensation_Calculation_Module SHALL 标记定位失败

### 需求10：理论坐标配置管理

**用户故事**：作为配方工程师，我希望通过独立接口管理理论坐标值，以便灵活调整基准位置。

#### 验收标准

1. THE Coordinate_Config_Module SHALL 为每个料架定位配方存储理论X、Y、Z坐标
2. THE Coordinate_Config_Module SHALL 支持按层号独立配置理论坐标
3. THE Coordinate_Config_Module SHALL 提供REST API接口供前端编辑坐标值
4. WHEN 前端提交坐标更新，THE Coordinate_Config_Module SHALL 验证数值格式
5. THE Coordinate_Config_Module SHALL 保存坐标修改历史记录
6. THE Coordinate_Config_Module SHALL 支持坐标值的小数点后三位精度

### 需求11：前端ROI绘制界面

**用户故事**：作为配方工程师，我希望在左侧窗口绘制ROI框，以便可视化配置定位区域。

#### 验收标准

1. THE Frontend_Module SHALL 提供左右双窗口布局
2. THE Frontend_Module SHALL 在左侧窗口显示点云投影或深度图
3. WHEN 用户在左侧窗口拖拽鼠标，THE Frontend_Module SHALL 绘制矩形ROI框
4. THE Frontend_Module SHALL 显示ROI框的坐标值
5. THE Frontend_Module SHALL 支持选择当前层号（1、2、3）
6. THE Frontend_Module SHALL 支持选择ROI类型（主ROI、支撑面ROI、前边缘ROI、立柱ROI）
7. THE Frontend_Module SHALL 提供保存ROI配置的按钮
8. THE Frontend_Module SHALL 提供复制上一层ROI配置的功能
9. THE Frontend_Module SHALL 提供重置ROI的功能

### 需求12：前端结果预览界面

**用户故事**：作为系统操作员，我希望在右侧窗口预览裁剪结果和补偿值，以便验证定位质量。

#### 验收标准

1. THE Frontend_Module SHALL 在右侧窗口显示ROI裁剪后的点云预览
2. THE Frontend_Module SHALL 显示当前层的三个补偿值（offset_x、offset_y、offset_z）
3. THE Frontend_Module SHALL 显示实际坐标值（actual_x、actual_y、actual_z）
4. THE Frontend_Module SHALL 显示定位置信度
5. THE Frontend_Module SHALL 显示ROI内有效点数量
6. WHEN 定位成功，THE Frontend_Module SHALL 以绿色显示结果状态
7. WHEN 定位失败，THE Frontend_Module SHALL 以红色显示结果状态并显示错误信息

### 需求13：前端参数输入与操作

**用户故事**：作为配方工程师，我希望输入和调整ROI参数，以便精确控制定位区域。

#### 验收标准

1. THE Frontend_Module SHALL 提供输入框以直接编辑X Min、X Max、Y Min、Y Max、Z Min、Z Max值
2. WHEN 用户修改输入框数值，THE Frontend_Module SHALL 实时更新ROI框显示
3. THE Frontend_Module SHALL 提供"采集点云"按钮触发点云采集
4. THE Frontend_Module SHALL 提供"自动填充ROI"按钮根据点云自动计算ROI边界
5. THE Frontend_Module SHALL 提供"预览裁剪"按钮显示裁剪后的点云
6. THE Frontend_Module SHALL 提供"保存ROI"按钮保存当前配置到数据库
7. WHEN 输入值无效，THE Frontend_Module SHALL 显示验证错误提示

### 需求14：Provider设计模式实现

**用户故事**：作为系统架构师，我希望使用Provider设计模式抽象数据来源，以便支持Mock和Real双模式。

#### 验收标准

1. THE System SHALL 定义 HandEyeProvider 接口，包含获取手眼标定矩阵的方法
2. THE System SHALL 实现 MockHandEyeProvider 提供模拟手眼标定矩阵
3. THE System SHALL 实现 RealHandEyeProvider 从标定文件或数据库读取真实矩阵
4. THE System SHALL 定义 RobotPoseProvider 接口，包含获取机器人位姿的方法
5. THE System SHALL 实现 MockRobotPoseProvider 提供三层预设拍照位姿
6. THE System SHALL 实现 RealRobotPoseProvider 从机器人控制器读取实时位姿
7. THE System SHALL 定义 DepthCameraProvider 接口，包含采集点云的方法
8. THE System SHALL 实现 MockDepthCameraProvider 生成模拟点云数据
9. THE System SHALL 实现 RealDepthCameraProvider 调用dm_camera模块采集真实点云
10. WHEN 系统配置为Mock_Mode，THE System SHALL 使用所有Mock实现类
11. WHEN 系统配置为Real_Mode，THE System SHALL 使用所有Real实现类

### 需求15：模拟手眼标定矩阵

**用户故事**：作为开发工程师，我希望使用预设的模拟手眼标定矩阵，以便在无真实设备时进行开发。

#### 验收标准

1. WHERE Mock_Mode 启用，THE MockHandEyeProvider SHALL 提供4x4变换矩阵 T_flange_camera
2. THE MockHandEyeProvider SHALL 设置相机相对法兰向前偏移120mm
3. THE MockHandEyeProvider SHALL 设置相机相对法兰向下偏移60mm
4. THE MockHandEyeProvider SHALL 设置相机相对法兰向右偏移30mm
5. THE MockHandEyeProvider SHALL 使用单位旋转矩阵（无旋转）

### 需求16：模拟机器人拍照位姿

**用户故事**：作为开发工程师，我希望使用预设的三层拍照位姿，以便在无机器人时进行开发。

#### 验收标准

1. WHERE Mock_Mode 启用，THE MockRobotPoseProvider SHALL 提供第1层拍照位姿
2. THE MockRobotPoseProvider SHALL 设置第1层位姿为 X=1000mm, Y=500mm, Z=600mm, RX=0, RY=0, RZ=0
3. THE MockRobotPoseProvider SHALL 提供第2层拍照位姿
4. THE MockRobotPoseProvider SHALL 设置第2层位姿为 X=1000mm, Y=500mm, Z=900mm, RX=0, RY=0, RZ=0
5. THE MockRobotPoseProvider SHALL 提供第3层拍照位姿
6. THE MockRobotPoseProvider SHALL 设置第3层位姿为 X=1000mm, Y=500mm, Z=1200mm, RX=0, RY=0, RZ=0
7. THE MockRobotPoseProvider SHALL 根据位姿计算4x4变换矩阵 T_base_flange

### 需求17：模拟点云生成

**用户故事**：作为开发工程师，我希望生成包含支撑面、立柱和噪声的模拟点云，以便测试定位算法。

#### 验收标准

1. WHERE Mock_Mode 启用，THE MockDepthCameraProvider SHALL 生成模拟支撑面点云
2. THE MockDepthCameraProvider SHALL 生成相机坐标系下 Xc 范围 -200mm 到 200mm 的点
3. THE MockDepthCameraProvider SHALL 生成相机坐标系下 Yc 范围 -100mm 到 100mm 的点
4. THE MockDepthCameraProvider SHALL 生成第2层支撑面 Zc 范围 800mm 到 820mm 的点
5. THE MockDepthCameraProvider SHALL 添加立柱点模拟侧边特征
6. THE MockDepthCameraProvider SHALL 添加边缘点模拟前边缘特征
7. THE MockDepthCameraProvider SHALL 添加高斯噪声点模拟真实噪声
8. THE MockDepthCameraProvider SHALL 返回包含宽度、高度和三维坐标数组的组织化点云

### 需求18：模式切换配置

**用户故事**：作为系统管理员，我希望通过配置文件切换Mock和Real模式，以便灵活控制数据来源。

#### 验收标准

1. THE System SHALL 从配置文件读取运行模式设置
2. THE System SHALL 支持配置项 RACK_3D_POSITIONING_MODE 值为 MOCK 或 REAL
3. WHEN 模式设置为 MOCK，THE System SHALL 实例化所有Mock Provider实现
4. WHEN 模式设置为 REAL，THE System SHALL 实例化所有Real Provider实现
5. THE Frontend_Module SHALL 显示当前运行模式（MOCK调试模式 或 REAL生产模式）
6. THE System SHALL 在日志中记录当前使用的模式

### 需求19：数据库模型扩展

**用户故事**：作为数据库管理员，我希望扩展现有模型以支持新的3D定位需求，以便存储完整的定位数据。

#### 验收标准

1. THE System SHALL 使用现有 RackLocationRecipe 模型存储配方数据
2. THE System SHALL 使用现有 RackLocationROI3D 模型存储多类型ROI配置
3. THE System SHALL 使用现有 RackLocationResult 模型存储定位结果
4. THE System SHALL 在 RackLocationRecipe 的 hand_eye_config 字段存储手眼标定矩阵
5. THE System SHALL 在 RackLocationRecipe 的 reference_feature_config 字段存储基准特征配置
6. THE System SHALL 支持每个配方关联多个 RackLocationROI3D 记录

### 需求20：REST API接口

**用户故事**：作为前端开发者，我希望有清晰的REST API接口，以便前端与后端通信。

#### 验收标准

1. THE System SHALL 提供 POST /api/vision/rack-3d/capture 接口触发点云采集
2. THE System SHALL 提供 POST /api/vision/rack-3d/calculate 接口执行定位计算
3. THE System SHALL 提供 GET /api/vision/rack-3d/recipes 接口获取配方列表
4. THE System SHALL 提供 GET /api/vision/rack-3d/recipes/{id}/rois 接口获取ROI配置
5. THE System SHALL 提供 POST /api/vision/rack-3d/rois 接口创建或更新ROI配置
6. THE System SHALL 提供 GET /api/vision/rack-3d/results 接口查询历史定位结果
7. THE System SHALL 提供 PATCH /api/vision/rack-3d/recipes/{id}/coordinates 接口更新理论坐标
8. WHEN 接收到无效请求数据，THE System SHALL 返回HTTP 400状态码和错误详情
9. WHEN 接收到有效请求，THE System SHALL 返回HTTP 200状态码和结果数据

### 需求21：点云数据格式与兼容性

**用户故事**：作为系统开发者，我希望统一点云数据格式，以便算法模块兼容不同来源的数据。

#### 验收标准

1. THE System SHALL 支持组织化点云格式（H × W × 3 数组）
2. THE System SHALL 支持非组织化点云格式（N × 3 数组）
3. THE System SHALL 将 dm_camera SDK 返回的点云数据转换为标准格式
4. WHEN 点云为组织化格式，THE System SHALL 保留宽度和高度信息
5. WHEN 点云为非组织化格式，THE System SHALL 直接处理 N × 3 坐标数组
6. THE System SHALL 使用 NumPy 数组作为内部点云数据结构
7. THE System SHALL 使用毫米作为坐标单位

### 需求22：错误处理与报警

**用户故事**：作为系统操作员，我希望系统能够检测并报告错误，以便及时处理异常情况。

#### 验收标准

1. WHEN 点云采集失败，THE System SHALL 生成ERROR级别报警
2. WHEN ROI内有效点数不足，THE System SHALL 返回 POINTCLOUD_ERROR 错误码
3. WHEN 定位置信度低于阈值，THE System SHALL 返回 LOW_CONFIDENCE 错误码
4. WHEN 补偿值超出允许范围，THE System SHALL 返回 OFFSET_OUT_OF_RANGE 错误码
5. WHEN 手眼标定配置缺失，THE System SHALL 返回 MISSING_HAND_EYE 错误码
6. WHEN PLC写入失败，THE System SHALL 生成ERROR级别报警并锁定工作站
7. THE System SHALL 在错误消息中包含描述性文本
8. THE System SHALL 将所有错误记录到日志文件

### 需求23：性能要求

**用户故事**：作为生产线管理者，我希望定位计算在合理时间内完成，以便不影响生产节拍。

#### 验收标准

1. WHEN 处理640×480分辨率点云，THE System SHALL 在2秒内完成单层定位计算
2. WHEN 处理1280×720分辨率点云，THE System SHALL 在5秒内完成单层定位计算
3. THE System SHALL 支持并发处理多个料架层的定位计算
4. THE Frontend_Module SHALL 在500毫秒内响应用户交互操作

### 需求24：日志与追溯

**用户故事**：作为质量工程师，我希望系统记录完整的定位过程，以便问题追溯和分析。

#### 验收标准

1. THE System SHALL 记录每次点云采集的时间戳
2. THE System SHALL 保存原始点云数据文件路径
3. THE System SHALL 保存结果可视化图像文件路径
4. THE System SHALL 在 result_data 字段记录完整的算法元数据
5. THE System SHALL 记录使用的配方ID和版本
6. THE System SHALL 记录机器人拍照位姿名称
7. THE System SHALL 记录点云有效点数量

### 需求25：Open3D集成

**用户故事**：作为算法开发者，我希望使用Open3D库处理点云数据，以便实现高级点云算法。

#### 验收标准

1. THE System SHALL 使用 Open3D 库进行点云可视化
2. THE System SHALL 支持将 NumPy 数组转换为 Open3D PointCloud 对象
3. THE System SHALL 使用 Open3D 实现 RANSAC 平面拟合
4. THE System SHALL 使用 Open3D 实现点云滤波功能
5. THE System SHALL 使用 Open3D 实现点云下采样以提高性能
6. THE System SHALL 使用 Open3D 计算点云法向量用于特征提取

### 需求26：测试支持

**用户故事**：作为测试工程师，我希望系统提供可测试的接口和模拟数据，以便验证功能正确性。

#### 验收标准

1. THE System SHALL 提供测试用的模拟点云生成工具
2. THE System SHALL 支持注入测试用的手眼标定矩阵
3. THE System SHALL 支持注入测试用的机器人位姿
4. THE System SHALL 提供测试用的ROI配置样例
5. THE System SHALL 支持跳过PLC写入步骤用于离线测试
6. THE System SHALL 提供单元测试覆盖核心算法模块
