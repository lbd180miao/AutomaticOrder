# 3D 工作台：单框点云模板中心匹配

工作台 `/vision/rack-locator/` 只使用 `cloud_center` 算法，旧双框算法及前端切换已删除。
两层料架框选一个交叉结构区域，三层料架框选两个区域，每个框同时包含横杆、立柱和连接处。
多尺度 ICP 对全部模板区域共同求解刚体变换，各区域参考点取采样后实测点的均值。

## 使用流程

1. 选择配方，采集点云或加载包含原图及组织化点云的数据包。
2. 选择料架层数，框选交叉结构区域并保存配方。
3. 在标准位置保存当前帧为点云标准模板。
4. 加载待测帧，开始计算，查看区域中心、匹配点云中心、匹配分数和机器人坐标偏差。

修改 ROI 或层数后必须重新保存模板。只有旧版模板的配方需重新示教，不会自动转换或回退。
现有 `cloud_center_config` 和 `cloud_center_reference` 可继续使用。数据库配方、标定和历史数据保留。

工作台、自动生产、PLC 调试、兼容 3D API 和离线数据包重算统一调用 `rack_cloud_service.evaluate_cloud`，
默认且唯一可用算法为 `cloud_center`。显式请求旧算法返回错误；旧模板不能参与定位。
数据包快照仅保存相机 ROI 及新算法配置、模板。历史坐标偏差重算仍可读取历史基准，不运行旧定位算法。

相机、单位、分辨率、ROI、匹配质量及 PLC 发布门限继续生效，`plc_publish_allowed=False`。
质量不合格只显示候选结果，不输出机器人补偿。

## 验证

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision --noinput
node --check static/vision/js/rack_dual_point.js
```
