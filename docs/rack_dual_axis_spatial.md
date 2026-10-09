# 三组空间 ROI / 双组轴线定位

工作台：`/vision/rack-locator/`。

1. 加载标准帧（组织化 H×W×3 点云，单位由现有点云加载器统一为 mm）。
2. 在深度伪彩图上分别框选 Π1 顶部横梁、Π2 左侧立柱、Π3 底部横梁。
3. 点击“生成 / 更新 3D 预览”。各框有效点的 min/max 生成独立 AABB；可调整向外扩充余量与下采样体素后再次预览。拖动点云视图检查覆盖。
4. 点击“保存配方”。数据库保存空间配置及双组标准轴线，同时写入 `MEDIA_ROOT/vision/rack_recipes/<recipe_id>/roi_config.json`。像素框、外框、像素测量线保留在配方中供编辑器回显，不参与空间算法取点。每次重新示教同时更新标准帧。
5. 点击“开始计算”，或调用生产定位入口。在线从整帧点云按保存 AABB 取点，不使用请求中的像素框。

算法：统计邻域离群点剔除，可选体素降采样，PCA 总最小二乘拟合三个构件的长轴。近似平行的轴线及无明确长轴的点簇返回失败。A 使用 Π1/Π2，B 使用 Π3/Π2，分别以两轴最近点中点构建独立坐标系。相对于示教坐标系计算各组变换、位移、XYZ 欧拉角、夹角与轴线间距。显示的位移是基准点移动量；`delta_T = T_current @ inverse(T_standard)` 是相机坐标系完整刚体变换，其平移列在有旋转时不等同于基准点移动量。层距是 A/B 基准点之间的三维距离。

2D 包围盒绘制连接 8 个顶点的 12 条边。投影映射从同帧有组织 XYZ/像素关系恢复，重投影误差超过 3 像素时报告不可投影，不使用猜测内参。投影、显示抽样不参与定位算法。

每条结果的 `result_data.groups.A/B` 保留独立结果。旧单组 PLC 寄存器不能表达两组补偿，因此不自动合并或下发，需要另行配置放置层与组别的映射。旧像素/三平面配方可继续按原算法计算；明确预览并保存标准后升级为双组算法。已保存的空间配方可重复计算，不需重新示教。

验证：

```powershell
.venv/Scripts/python.exe manage.py test apps.vision.test_rack_spatial apps.vision.test_roi_recipe_save apps.vision.test_rack_workbench_feedback --noinput --testrunner django.test.runner.DiscoverRunner
node --check static/vision/js/rack_locator_workbench.js
```

覆盖空间筛选与像素顺序无关、独立构件位移、刚体旋转、无效点/平行退化、投影恢复、预览/保存/重载、签名校验、像素位置保存回显且不会进入空间计算、旧结果保存入口兼容。

空间参数在工作台与 3D 配方管理中共用 roi_config.margin_mm / voxel_mm，默认 5 / 0 mm。保存后重新加载配方即可回显。修改扩充量按新旧差值更新三个 AABB，重复保存不会重复扩充；标准轴线保持不变。计算使用数据库中的当前配置，roi_config.json 为示教时导出快照。

主轴方差比阈值为 1.5，低于阈值仅记录 quality_warnings 并继续计算。警告包含标准帧/当前帧、区域及实测比值，随结果保存并在机器人偏差面板显示。有效点不足、无空间跨度或无法构建坐标系仍返回失败。
