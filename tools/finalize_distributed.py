"""Finalize two complete application roles without historical media."""
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from packaging_resources import is_visual_data, is_ui_asset, copy_resources

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get('DISTRIBUTED_OUTPUT', ROOT / 'delivery/full-dual'))
STAGE = ROOT / 'build/distributed_seed'
agv = OUT / 'AGVControl'
external = OUT / 'ExternalControl'
agv_only = '--agv-only' in sys.argv
if not agv_only and external.exists():
    raise RuntimeError('ExternalControl output already exists; use a new release directory.')
if (agv / 'media').exists():
    raise RuntimeError('Deployment output unexpectedly contains media.')
for file in agv.rglob('*'):
    if file.is_file() and is_visual_data(file) and not is_ui_asset(file.relative_to(agv)):
        raise RuntimeError(f'Deployment output contains an excluded file: {file.relative_to(agv)}')
copy_resources(agv)
if not agv_only:
    shutil.copytree(agv, external)
    (external / 'AGVControl.exe').rename(external / 'ExternalControl.exe')
for folder, role in ([(agv, 'agv')] if agv_only else [(agv, 'agv'), (external, 'external')]):
    # New-install snapshots must not inherit a developer's trigger levels/jobs.
    # Field upgrades use --data-dir and retain their own durable state.
    with sqlite3.connect(folder / 'db.sqlite3') as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('DELETE FROM workflow_stationcycle')
        db.execute('DELETE FROM devices_plclistenerlog')
        db.execute('DELETE FROM devices_plclogwindow')
    executable_name = 'AGVControl.exe' if role == 'agv' else 'ExternalControl.exe'
    (folder / '使用原数据启动.cmd').write_text(
        '@echo off\n'
        'if "%~1"=="" goto usage\n'
        'if not exist "%~1\\db.sqlite3" goto usage\n'
        f'"%~dp0{executable_name}" --data-dir "%~1"\n'
        'exit /b %errorlevel%\n'
        ':usage\n'
        'echo Drag your OLD application data folder onto this CMD file.\n'
        'echo The folder must contain db.sqlite3 and deployment.json.\n'
        'pause\n', encoding='ascii')
    (folder / 'deployment.json').write_text(json.dumps({
        'role': role, 'plc_auto_start': role == 'agv', 'camera_auto_start': role == 'agv'
    }, indent=2), encoding='utf-8')
    cfg = json.loads((STAGE / 'agv_gateway.json').read_text(encoding='utf-8'))
    if role == 'external':
        cfg['gateway_url'] = 'http://127.0.0.1:8001'
        shutil.copy2(STAGE / 'gateway.json', folder / 'gateway.json')
        (folder / 'MES网关工作台.url').write_text('[InternetShortcut]\nURL=http://127.0.0.1:8001/\n', encoding='utf-8')
    (folder / 'agv_gateway.json').write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    (folder / '部署说明.txt').write_text('''双机完整功能部署包

两台电脑均包含完整的 PLC、视觉、MES、配方、数据库和管理功能；数据库独立，不自动同步。
AGV 电脑：复制 AGVControl 整个文件夹，双击 AGVControl.exe。
外部电脑：复制 ExternalControl 整个文件夹，双击 ExternalControl.exe。
完整软件页面均自动打开 http://127.0.0.1:8000。
首次部署：将文件夹放到固定位置，运行 EXE 即自动为当前 Windows 用户注册开机登录启动，无需另点启用脚本。
之后开机登录该用户时自动启动 exe 并打开浏览器；无需管理员权限，不会修改 Windows 自动登录设置。
移动目录后运行一次新位置的 EXE，自动更新启动路径。可在 Windows 启动应用中禁用；清理旧版启动项，避免同时启动旧版。
外部软件同时启动 HTTP MES 网关，监听 0.0.0.0:8001。网关工作台在本机 http://127.0.0.1:8001。
无需另开 MESGateway.exe，不要同时运行旧版网关或同一程序多个副本。

通信链路：PLC → AGV → HTTP → 外部电脑 → 公司 MES → 外部电脑 → HTTP → AGV → PLC。
AGV 的 MES 请求只发往 agv_gateway.json 的 gateway_url，不直接访问公司 MES。
AGV 默认地址 192.168.3.6，外部电脑地址 192.168.3.10；若现场不同修改 AGV 的 gateway_url。
外部电脑连接 AGV视觉 WiFi，同时保留公司内网连接；网关通过公司内网访问 MES。
AGV WLAN 192.168.3.6 与外部电脑 WLAN 192.168.3.10 通过边缘路由器连接；确保 AGV 可访问 192.168.3.10:8001，并关闭无线客户端隔离。
外部电脑防火墙允许 AGV 访问 TCP 8001，边缘路由器不要开启客户端隔离。
不要求网关监听 TCP 8000；8000 是各电脑自己的完整软件界面。
外部 gateway.json 配置 MES 地址、工厂、产线、认证；两端 token 必须一致。
外部 agv_gateway.json 指向本机 127.0.0.1:8001，不要改成 AGV 地址。

AGV 随 exe 启动自动监听 PLC，失败每 5 秒重连，日志 logs/plc-listener.log。
监听 DB2：产品条码 DBB0、料框码1 DBB24、料框码2 DBB46（均 STRING[20]）；3D DBX68.3、封箱1/2 DBX68.5/68.6、料箱工作中1/2 DBX68.7/69.0。泡棉 DBX68.4 已停用。
五个 Bool 启动/重连先建立基线，只接受实际 False→True；保持 True 不重复，PLC约5秒后自行复位，上位机不复位输入。
三个条码分别按上次有效值去重，空值/NoRead不清除有效码；恢复原码不重复查询MES。
料框码1/2变化分别查询MES第1接口，映射后分别写 DBW100/102 料架种类。
新的有效产品码等待料箱工作中上升沿，绑定当次对应料框并上传；原码已受理后，即使再次触发或切换料箱也不重复绑定上传。
封箱1/2上升沿分别锁定对应料框，调用MES第3接口；任务排队不改变条码归属。
XYZ仅写 DBD76/80/84/88/92/96，两料架共用结果，每次覆盖。AGV监听在线时每0.5秒翻转 DB2.DBX70.0 心跳（False→True→False循环）；拍照和MES处理期间仍更新，PLC无需周期清零。除这些输出和两路料架种类外，不读写其他反馈或锁定位。
单路失败记录报警，不阻断独立视觉通道。MES结果不明时先核对，不重复提交。
报警记录可展开详情，按单个年月日查询当天记录。NoRead 是扫码失败标记，不作为料框码提交 MES。
独立输入采样在相机计算期间继续运行；PLC 读写仍串行，避免通信并发冲突。
不再监听旧产品扫码、料框到位和配方校验触发位；装箱完成调用 MES 第三接口获取区位号并保存料框/轮次关联。
外部端启动时保持 PLC 和相机自动启动关闭，避免争抢同一硬件；仍可按需手动使用。
AGV 随程序持续监听，旧环境变量中的关闭标记不能关闭 AGV 自动监听；外部端保留手动操作。
外部端如需手动启动 RVC 相机服务，使用本机 8002 端口，避开 MES 网关的 8001。
3D 由 PLC 触发拍照定位，读取已保存的 3D 默认配方。2D 相机持续采集和检测，不等待 PLC 触发、不回写 PLC；最新 OK/NG 覆盖显示，不保存实时视频历史。每次确认 NG 的结果和时间保存到数据目录 foam_ng.sqlite3，检测页日志可查看当天记录；后续 OK 不删除 NG 历史。
双料框监听固定采用上升沿模式，禁用旧高电平重复业务调试。
历史左侧为相机 2D 原图，右侧为配方 ROI 标注 2D 图；旧记录未保存 2D 图时无法还原。
默认配方设置随数据库交付；配方缺失或停用时，请重新选择有效配方。
关闭浏览器不退出程序，关闭程序控制台才停止服务。
主服务异常退出时窗口保留，显示退出码，按回车关闭；不要把退出码提示当成仍在运行。
排查日志：logs/server.log、startup-error.log、native-crash.log、rvc-native-crash.log。
相机未连接不影响网页运行；相机进程故障仅重启相机，不自动重启主程序或重复硬件任务。
相机厂家驱动需在连接相机的电脑安装；完整复制文件夹，无需 Python。

本次部署包仅按资源白名单保留配方引用的标准模板，排除历史采集、诊断图片、点云、离线包和 SDK 示例。
标定、配方、设备参数保留在数据库中，随包保留相机参数文件；视觉任务、检测结果、图像记录和料架测量历史已从打包快照清除。
resource-manifest.json 记录本次媒体资源清单。
升级前停服备份，保留现场数据库、配置、任务账本及模板，不要覆盖现场数据。

验收：先启动外部软件，再启动 AGV 软件。
AGV MES 页面 → AGV电脑与外部电脑通信 / 网关连接状态：测试网关连接、运行通信自检。
外部 MES 网关工作台：测试 MES 连接。之后使用真实料框码进行只读查询，最后做 PLC 触发联调。
断网任务保留并恢复；MES 写操作结果不明确时需核对，不能盲目重复绑定/封箱。
''', encoding='utf-8-sig')
print('Created complete uncompressed deployments:', agv if agv_only else OUT)
