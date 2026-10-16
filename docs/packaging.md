# Windows 打包与部署

在已经能正常运行项目及相机功能的 Windows Python 环境中构建，Python 位数和版本必须兼容 PyRVC、chg_hik 等原生扩展。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.ps1
```

脚本先检查依赖，再收集静态文件，最后使用 `MyApp.spec` 构建。不会自动安装相机驱动。输出是整个 `dist\MyApp` 文件夹，必须完整复制其中所有文件和子目录，不能只复制 EXE。构建会替换已有构建输出，请勿把现场数据库保存在构建目录后再次构建。

## 持久数据

构建不包含 `media` 历史图片和点云；数据库仍随包提供。需要查看历史数据时，另行部署对应的 `media`，或使用 `--data-dir` 指向已有数据目录。

建议停服后备份并复制原有 `db.sqlite3`、整个 `media` 到独立数据目录，例如 `D:\AutomaticOrderData`，再运行：

```powershell
.\MyApp.exe --host 127.0.0.1 --port 8082 --data-dir D:\AutomaticOrderData
```

不指定 `--data-dir` 时，默认使用 EXE 同级目录的数据库和 media。不要把数据库放进 `_internal`。程序不会自动迁移数据库；新建数据库或升级数据库结构应先在匹配版本的源码环境执行 `python manage.py migrate`，再停服部署数据库。复制运行中的 SQLite 数据库前应停止写入，避免不一致。

## 硬件与额外资源

- 海康 2D：目标机器安装 MVS Runtime 和 Python 示例绑定。代码从 `MVCAM_COMMON_RUNENV\Samples\Python\MvImport` 加载官方绑定；未设置该变量时使用 `C:\Program Files (x86)\MVS\Development\Samples\Python\MvImport`。按安装位置配置 `HIK_CAMERA_SDK_LIB_DIR`。`.mfs` 参数文件已随包收集。
- `chg_hik`：构建环境已安装时会收集；走此备用采图路径时，检查包内 `Env.json` 的 SDK 路径符合目标机器安装位置。
- RVC 3D：构建环境必须安装可用的 PyRVC，目标机器仍需安装匹配的厂家 SDK/驱动。打包包含 Python 包不等于安装设备驱动。
- 旧 DM：如需使用，构建前补齐 `apps\dm_camera\sdk\lib` 中厂家 DLL 及依赖。当前仓库没有此目录，无法保证旧 DM 实机功能。
- 离线点云：大体积 `3d_SDK\pic` 不自动打包。复制到现场数据目录，并设置 `OFFLINE_DATA_PACKAGE_DIR` 指向该目录。
- 数据库内已有的绝对图片路径或标定文件路径，应检查在目标机器仍有效。

## 验收

### PLC 常驻监听

设备状态页 `/devices/status/` 顶部的“PLC全局”按钮可手动启动完整自动流程。页面显示“已启用（后台监听中）”后，刷新或关闭网页不会停止监听；再次点击同一按钮可关闭全局监听。关闭时等待当前扫描或拍照回写完成，页面显示“正在关闭”；完成后可再次启动。监听已启用不代表 PLC 通信成功，通信状态仍以页面连接状态和日志为准。退出程序后监听停止，下次启动默认关闭，需要再次点击按钮。

正常启动 `MyApp.exe`、`run.py` 或 `manage.py runserver` 时，默认不启动 PLC 后台监听，打开网页也不会启动自动工位流程。如需恢复自动监听，请在启动服务前显式设置环境变量 `PLC_LISTENER_AUTO_START=true`。启用后每 0.25 秒轮询 PLC 工位流程，浏览器关闭不影响监听；连接失败后每 5 秒重新创建连接并重读设备配置，日志在数据目录 `logs/plc-listener.log`。打包、迁移、测试和相机子进程不会启动 PLC 监听。

沿用现有 DB2 工位状态机：定位阶段处理 3D 定位触发，配方校验阶段处理 2D 测量，泡棉阶段处理 2D 检测。触发需保持至完成确认并复位；不是任意阶段、任意短脉冲都会拍照。工位锁定或手动调试占用期间不会自动执行正常流程。无需再另开 `run_workflow_worker`。

PLC 地址、Rack、Slot、端口取自当前数据目录数据库内启用的 PLC 设备；部署旧数据库时请在设备配置中核对。网页可访问不代表 PLC 的 S7 通信成功，具体连接/DB 读取错误查看上述日志。

### 相机连接故障排查

- `0x8000000c` 是 MVS 动态加载 DLL 失败，不是曝光错误。2D worker 现在先显式加载 `HIK_CAMERA_SDK_LIB_DIR` 中的 MVS，再枚举 GigE/USB；不再要求无关的 CameraLink/CXP/XoF 采集卡插件。
- PyRVC 的 DLL/CTI 位于 site-packages 根目录，单独 `collect_all('PyRVC')` 无法完整收集动态插件。打包脚本现在根据 PyRVC 安装清单补齐运行时文件，并携带 `3d_SDK/rvc.json`。现场仍需安装厂家驱动。
- 3D 连接或采集失败会保留真实错误，不再进入模拟图片分支覆盖原始异常。查看数据目录下 `logs/rvc-service.log`；仅凭 `cannot unpack non-iterable NoneType object` 不能判断 IP 或曝光。
- 默认 3D 目标 IP 为 `169.254.10.202`，现场若不同，在启动 EXE 前设置 `RVC_CAMERA_IP`（或用 `RVC_CAMERA_SN` 指定序列号）。目标电脑连接相机的网卡须与相机网络配置匹配；不要改动向日葵正在使用的联网网卡。


先在无源码、无 `.venv` 的目标目录启动，检查 `/devices/status/`、静态资源和历史图片。然后连接现场设备分别验证 PLC、2D 采图、RVC 3D 采图和退出后的子进程清理。没有硬件连接的构建测试不能代替实机验收。

仅检查参数入口可运行 `MyApp.exe --help`。构建过程中暂时关闭 RVC 自动启动，不会改变正式运行时的默认配置。


### RVC 采集参数来源

相机服务以 `3d_SDK/rvc.json` 为默认参数来源（源码运行相对项目根目录，打包运行优先使用程序旁的文件）。每次拍照重新加载文件，并传入 SDK CaptureOptions；文件缺失、JSON 无效或参数无法应用时返回错误，不退回相机内部默认参数。

曝光、增益、ROI、滤波、HDR 等 SDK 支持字段会应用。`cameraId`、`coordinateSelect`、`customCoordinate*`、`bandwidth_int`、`filter_range`、`phase_filter_range` 等当前 CaptureOptions 不支持的字段通过日志及 `unsupported_config_fields` 返回；点云坐标仍与预览相机通道保持一致。手眼矩阵和机器人拍照位姿仍保存在数据库。

页面设置模式/曝光会原子写回此 JSON；连接时不再用 Django settings 默认值覆盖。单次 capture 请求显式传入的模式/曝光仅覆盖该次拍照。`save_2d` 控制文件输出，实际是否采集二维图像由 JSON 的 `enable_2d_in_capture` 决定。

升级代码后需要重启 RVC 独立相机服务；此后仅编辑 JSON 不需要重启。模式数值使用已安装 SDK 枚举（当前 Fast=1、Normal=2、Ultra=4）。普通拍照接口仍不支持需要运动配合的线扫模式。
