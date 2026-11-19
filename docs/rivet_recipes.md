# 铆钉配方与 PLC 差值

2D 已移除旧配方库、单图示教入口、配方增删改查与导入导出入口。旧接口返回停用错误；历史数据库记录、标定与既有历史检测数据保留。连续泡棉算法仍使用其独立标准模板，不再选取旧 2D 配方。

3D 配方在 `roi_config.cloud_center_config` 保存算法类型 rivet、料架层数、布局、图像尺寸及各铆钉 ROI 的 x/y/width/height（原图像素）。`cloud_center_reference` 保存算法版本、相机标识、标准测量、各点相机 XYZ、相对 P3 向量、示教时间及可用的拍照姿态。沿用字段名以保持已有数据库和导出文件兼容。

- 普通两层/三层：P1、P2、P3，A 为 P1 相对 P3，B 为 P2 相对 P3。
- 两层下料框：P1、P3，A 为 P1 相对 P3，B 写零。
- 相机系差值为当前相对向量减标准相对向量。机器人系差值只进行标定旋转，避免整架平移影响横杆相对偏差。
- 配方页显示 ROI、标准 XYZ、相对向量、检测分、有效点/采样点及状态。工作台显示当前数据、标准对比、相机系差值及机器人系差值。

自动工序保持原有 PLC 触发后检测回写路径。工作台新增“发送差值到 PLC”，只有当前检测通过时可用；示教、导入及离线检测不会自动写 PLC。后端重查当前配方、ROI/标准模板一致性、点配置、标定结果、坐标系、有限数值及限值。手动调试互斥期间拒绝工作台发送。

PLC DB2：A 组 ΔX/ΔY/ΔZ 为 DBD76/80/84；B 组为 DBD88/92/96，均为 REAL、mm。沿用适配器六值预校验及写后回读。修改模板或 ROI 后必须重新检测，改层数后必须重新示教。

验证：`manage.py test apps.vision.tests_rack_rivet apps.vision.tests_foam_stream apps.devices.tests_camera_worker apps.workflow.tests_dual_rack.RoutingTests`；`node tools/test_rivet_recipes_ui.cjs`。PLC 回写测试使用内存适配器，不向现场设备发送测试数据。
