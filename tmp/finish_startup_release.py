from pathlib import Path
import hashlib
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.packaging_resources import is_visual_data

source = ROOT / 'build/diagnostics-final/AGVControl'
release = ROOT / 'delivery/20261112-Startup-Diagnostics-v4b'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


bundle = {p.relative_to(source): p for p in source.rglob('*') if p.is_file()}
assert Path('AGVControl.exe') in bundle
changed = 0
for name in ('AGVControl', 'ExternalControl'):
    folder = release / name
    assert (folder / 'deployment.json').is_file()
    for relative, original in bundle.items():
        target = folder / (f'{name}.exe' if relative == Path('AGVControl.exe') else relative)
        if not target.is_file() or digest(original) != digest(target):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            changed += 1
    (folder / '使用原数据启动.cmd').write_text(
        '@echo off\nif "%~1"=="" goto usage\n'
        'if not exist "%~1\\db.sqlite3" goto usage\n'
        f'"%~dp0{name}.exe" --data-dir "%~1"\nexit /b %errorlevel%\n'
        ':usage\necho Drag your OLD application data folder onto this CMD file.\n'
        'echo The folder must contain db.sqlite3 and deployment.json.\npause\n', encoding='ascii')
    manifest = json.loads((folder / 'resource-manifest.json').read_text(encoding='utf-8'))
    allowed = {item['path']: item['bytes'] for item in manifest['files']}
    for path, size in allowed.items():
        assert (folder / path).stat().st_size == size
    for p in folder.rglob('*'):
        if p.is_file() and is_visual_data(p):
            assert p.relative_to(folder).as_posix() in allowed, p
    assert not (folder / '2d_SDK/pic').exists()
    assert not (folder / '3d_SDK/pic').exists()
    assert not (folder / 'logs').exists()
    assert all(p.suffix.lower() == '.mfs' for p in (folder / '2d_SDK').rglob('*') if p.is_file())
    print(name, 'validated', len(bundle), 'bundle files;', len(allowed), 'allowlisted assets')

(release / '现场升级说明.txt').write_text('''启动稳定性修正及诊断版（2026-11-12）

1. 停止旧程序，保留并备份现场旧目录。不要用新包数据库覆盖现场数据库。
2. 把本包完整 AGVControl 文件夹复制到 AGV 电脑的一个新目录，例如 AGVControl-新版。
   不能只复制 EXE。外部电脑使用完整 ExternalControl 文件夹，同样放在新目录。
3. 若继续使用现场数据，将旧程序文件夹拖到新目录内的“使用原数据启动.cmd”上。
   此入口通过 --data-dir 继续使用旧数据库、media、角色配置和 MES 网关账本，
   不复制或覆盖这些数据。日志也会写入旧数据目录的 logs。
   如现场改过相机参数，启动前将旧 3d_SDK/rvc.json 及所用 2d_SDK/*.mfs
   参数文件单独复制到新程序的对应位置；不要复制整个 SDK 目录。
4. 若无现场修改、直接使用本次配套数据，双击新目录里的 AGVControl.exe 即可。
5. 相机未连接时设备可显示离线，但网页应正常打开；PLC 仍按 AGV 角色自动监听。
   外部端保持完整功能，默认不自动连接硬件；AGV 的 MES 仍经外部 HTTP 网关转发。

本次修改：限制数值库默认线程数量，减少多进程内存占用；主服务异常退出时保留
启动窗口及退出码；保存 Python 异常和原生崩溃记录；修正中文日志编码。
没有自动重启主服务，避免重复执行硬件任务。相机子进程仍可独立恢复。
现场截图不足以确定根因；本机曾复现 OpenBLAS 内存分配失败，但不能据此断言现场相同。

如网页仍无法打开，请把 logs/server.log、startup-error.log、native-crash.log、
rvc-native-crash.log、rvc-service.log、plc-listener.log 中存在的文件发回排查。
不要只拍启动时最后一行。若窗口显示异常退出，记录完整退出码后再按回车关闭。

本包未压缩。仅保留配方引用的标准模板及相机参数，不包含历史采集、诊断图片、
点云、临时上传或 SDK 示例。配方、标定记录保留在数据库中。
''', encoding='utf-8-sig')
print('Updated files:', changed)
print('EXE SHA256:', digest(release / 'AGVControl/AGVControl.exe'))
