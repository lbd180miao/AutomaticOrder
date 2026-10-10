# dist 运行与数据迁移

## 2026-10-10 相机随网页后台退出

自动启动的 RVC 服务通过专用标准输入管道绑定网页后台进程。正常退出、关闭控制台窗口或强制结束网页后台后，相机服务检测到管道关闭，释放 SDK 并退出；SDK 阻塞时 10 秒后强制退出。相机异常退出时仍由网页后台重启。

这指网页后台进程的启停，关闭浏览器标签页不会停止后台。手动启动或启动前已存在的相机服务仍属独立服务，不由网页后台接管。升级时需先关闭旧相机服务，源码入口重启后生效；已有 exe 需要重新打包。

验证：9 项相机服务回归测试通过，包含正常关闭管道与强制结束父进程后的资源释放；未连接真实相机执行测试。

## 2026-10-09 本轮性能修复

本轮输出目录为 `dist-optimized/AutomaticOrderFull`。旧 `dist` 下的 exe
修改时间为 21:44:50，不包含后续源码修复；请关闭旧程序后启动新目录内的 exe。
整个输出目录需要一起部署，不能仅复制 exe。

* NumPy 三平面算法不再提前加载 Open3D。本机独立进程导入耗时由约 3.102 秒降为 0.016 秒。
* 工作台显示用预览、标注图使用 JPEG 90；原始 `.npy` 和归档深度 PNG 保留。
  1280×960 合成噪声图编码对比：PNG 3,693,953 字节 / 31.3 ms，JPEG 1,101,558 字节 / 8.9 ms。
  实际图片收益取决于内容，这些数字不代表现场端到端速度。
* 三平面计算响应附带 `timings`，后台打印读取裁剪、拟合、A/B 换算、总耗时；
  页面显示总耗时和 A/B 失败原因。计算期间不能切换配方。
* 缺失结果图片显示单独说明，不影响已有数值显示。去掉时间戳查询参数，避免强制重新获取同一图片。
* 质量日志不再声称必然拦截；是否拦截仍由各调用方原有逻辑决定。

历史图片 404 表示请求的文件在当前 media 中不可用；优化不会恢复丢失的图片。
图片访问路由与权限保持原有行为，未新增在 DEBUG=False 下公开 media 的功能。

验证：11 项 Django 回归测试通过；前端语法及 A/B 成功/失败 DOM 渲染验证通过。
真实相机采集与现场补偿仍需使用实际标准数据验证。

打包与线程数是两件事。新版入口默认使用 8 个 Waitress 工作线程，启动时可调整：

```powershell
.\AutomaticOrderFull.exe --threads 8
```

也可用 `WAITRESS_THREADS` 环境变量。更多线程主要缓解请求等待，不保证缩短单次点云计算。相机 SDK 仍由独立服务进程串行保护。

源码默认使用项目根目录的数据库和 media；冻结程序默认使用 exe 同目录的数据，不在临时解包目录写入。可以明确指定持久数据目录：

```powershell
.\AutomaticOrderFull.exe --threads 8 --data-dir D:\AutomaticOrderData
```

该目录需要配套的 `db.sqlite3` 和完整 `media`。程序不会自动复制或覆盖旧数据库。已有 `DJANGO_DATABASE_PATH` / `DJANGO_MEDIA_ROOT` 环境变量优先于此配置。

重新打包前运行：

```powershell
.\.venv\Scripts\python.exe manage.py check_rack_references
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --distpath dist-fixed --workpath build-fixed AutomaticOrderFull.spec
```

使用新输出目录，避免覆盖正在运行的旧 dist 及现场数据。检查失败时，先恢复准确的标准原始点云及 `.units.json`，或者重新采集标准料架并保存标准。不能用当前料架点云冒充旧标准。

本次排查发现配方 #8 引用标准 #337，但其 `vision/rack_workbench/2026/10/09/rack_workbench_125128_049222.npy` 在源码和旧 dist 的 media 中均缺失，且没有 A/B 双组快照。代码无法还原这些丢失的数据。现有保存标准流程会生成双组快照，重新保存有效标准后不必每次从原始点云重建轴线。

层距必须使用与预览图逐像素对应的组织化点云。已修复加载上次数据接口固定返回 640×480 的错误。无深度区域仍会拒绝计算，并显示端点坐标、点云尺寸和有效点数；此时需要在同一待测表面重新示教端点或改善采集，不能通过降低点数要求伪造结果。

## 2026-10-10 PLC 3D 联调修复

- PLC 调试对三平面/空间 ROI 配方固定选取 `robot_groups.A.translation_mm`，对应第一组机器人基坐标补偿：X → DB2.DBD50，Y → DBD54，Z → DBD58。B 组暂不写入。保留配方 XYZ/Rz 限值、有限值检查、写后回读和完成握手；缺少 A 组或标定时返回失败值 999，不能回退到旧补偿。
- 静态脚本未成功初始化时，开始按钮保持禁用并显示部署提示；表单禁止普通刷新。固定 JS MIME 类型为 text/javascript，防止 Windows 将脚本标为 text/plain 后被 nosniff 拦截。
- 三个打包入口统一到 AutomaticOrderFull.spec，打包前自动 collectstatic，构建期间关闭相机自动启动。输出程序名统一为 AutomaticOrderFull.exe。
- PLC 联调租约文件使用 DATA_DIR/logs，支持 --data-dir 指定可写持久目录。
- 本轮输出到 dist-plc3d/AutomaticOrderFull，不覆盖旧 dist 或现场数据库。复制完整目录后启动新 exe。旧 exe 不会随源码修改自动更新。
- 配方 8/标准337 和配方9/标准222 的原始点云在当前数据目录缺失。恢复对应文件和单位文件，或在标准料架就位后重新保存标准，才能计算正确的 A/B 偏差。
