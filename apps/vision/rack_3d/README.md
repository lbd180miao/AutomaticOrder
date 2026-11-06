# 3D 料架定位兼容接口

`services.py` 的 `RackPositioningService` 统一调用 `rack_cloud_service.evaluate_cloud`，唯一定位算法为 `rack_cloud_match` 点云模板匹配。

配方必须在工作台保存 `roi_config.cloud_match_config` 四个像素区域以及 `cloud_match_reference` 标准点云模板。旧平面、边缘、立柱和刚体模板不参与计算，也不作为失败回退。

Provider 负责采集，`processors.py` 保留坐标转换和通用点云预处理。采集、计算和历史查询路由见 `urls.py`。历史 ROI 只供读取，不驱动定位。

匹配结果仍受原有 PLC 发布门限约束；本次清理不启用 PLC 写入。

验证：`python manage.py test apps.vision.tests_cloud_service apps.vision.tests_cloud_match`
