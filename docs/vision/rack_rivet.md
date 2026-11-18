# 三铆钉料架定位

适用工况：料架底部机械限位，整体位置固定。不求解整架位姿，不加入整架平移补偿。

1. 在同帧二维原图上分别框选 P1（上横杆）、P2（下横杆）、P3（竖杆固定参照）。框内尽量只含一个铆钉，三个编号不能互换。两层/三层配置均需三个铆钉，并输出两组补偿。
2. 在参考状态点击“保存当前帧为铆钉标准模板”，保存三个相机 XYZ，以及 r10=P10-P30、r20=P20-P30。
3. 运行时重新检测三个铆钉，计算 δ1=(P1-P3)-r10、δ2=(P2-P3)-r20。
4. 使用手眼工作台的 R_base_flange × R_flange_camera 旋转偏差向量；不使用平移项。A 组 XYZ 对应上横杆，B 组 XYZ 对应下横杆，沿用现有 PLC 六个 REAL 点位。

旧点云配准模板不会自动转换，必须重新框选并保存。数据库其他配方、标定数据保持不变；为兼容存储，仍使用 cloud_center_config / cloud_center_reference 键，内容以 algorithm=rivet、version=rivet_relative_v1 区分。

算法来自 `C:\Users\11410\Desktop\maoding\铆钉算法` 的 localize_rivets.detect_image 和 measure_with_fallback。四个实现文件仅改为包内相对导入，检测、取点参数和稀疏取点回退保持原样；SOURCE.json 记录原文件 SHA256。所需外观标准模板 head_patterns.npz 纳入资源白名单，不复制采集图、点云或诊断输出。

外层对每个编号进行候选选择：无候选、第二候选排名超过第一候选的 85%、重复中心、无有效 XYZ 均拒绝补偿；沿用原 standalone 主程序的歧义比例。机器人转换失败、拍照旋转与模板不一致、任一组超过配方 XYZ 限值也拒绝有效补偿。

检测分不是准确率。原算法三维输出是邻域表面估计（包括原 SPARSE_ESTIMATE 分支），未因本次接入获得现场精度认证。上线前需用实际参考帧重新示教，并验证 A/B 位置、轴向、单位及现场重复性。

验证入口：`python manage.py test apps.vision.tests_rack_rivet`，覆盖模板保存/重载、运行/历史接口、共同平移抵消、独立双组旋转、失败与限值校验。未连接真实 PLC 或相机。
