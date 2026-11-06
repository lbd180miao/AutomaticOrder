# 3D 工作台：点云模板匹配

工作台 `/vision/rack-locator/` 只提供点云模板匹配。四 ROI 用于选择模板中的稳定结构区域；P1、P2 是区域参考点，不再计算灰度边缘交点。

## 使用流程

1. 选择配方，采集点云或加载含 `image2d.png`、`pointcloud.npy` 的数据包。
2. 在原图上框选四个区域，点击「保存配方」。
3. 在标准位置点击「保存当前帧为点云标准模板」。
4. 加载待测帧，点击「开始计算」，查看匹配质量、相机坐标和机器人坐标偏差。

修改区域后应重新保存点云模板。匹配需要明确的点云单位、相机坐标系和足够的有效结构点；模板与当前点云的相机标识、分辨率须一致。结果仍遵守现有质量门限，不自动写 PLC。

## 后端

- `rack_cloud_match.py`：模板构建、多尺度 ICP、匹配质量校验与参考点投影。
- `rack_cloud_roi.py`：区域标识及像素边界校验，与找边算法无关。
- `rack_cloud_package.py`：读取离线采集数据，无定位算法依赖。
- `rack_dual_point_views.py`：保留现有 URL 前缀，提供 prepare、image、depth、save、cloud-match。
- `rack_robot_points.py`：机器人坐标转换。

配方仅从 `cloud_match_config` 和 `cloud_match_reference` 读取当前定位配置与模板。不再根据 `localization_mode` 选择算法，不回退到 `dual_point` 或旧交点模板。旧配方字段及历史记录不做破坏性迁移。

已移除四 ROI 找边的 Projection/CaliperFit 实现、自动找边 ROI、二维/三维交点检测、旧示教及专用离线 CLI。旧工作台 calculate、save、spatial-teach 接口也已移除。历史记录的机器人偏差重算保留，它只转换已有坐标，不执行旧定位算法。三平面共享服务、旧刚体/开口矩形/轴线算法及其离线诊断工具均已删除。生产触发、PLC 调试、离线重算和兼容 3D API 统一调用 `rack_cloud_service.py`。旧记录由 `rack_position_history.py` 读取，不再依赖旧算法。

## 验证

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision --noinput
node --check static/vision/js/rack_dual_point.js
```

接口回归覆盖无模式参数的模板保存/匹配、旧模式不能恢复找边、原图与点云帧令牌、ROI 边界校验、旧路由不可达，以及原图/深度预览。

未保存 `cloud_match_reference` 的配方必须先建立点云标准模板，旧三平面配置不再作为计算回退。匹配结果原有 `plc_publish_allowed=False` 门限保留，算法清理不会自动开启 PLC 写入。
