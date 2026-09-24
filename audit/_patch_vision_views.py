# -*- coding: utf-8 -*-
"""一次性补丁：vision/views.py 的 3D 相机自检接口切换到 RVC。"""
from pathlib import Path

path = Path(r"D:\workspace2\AutomaticOrder\apps\vision\views.py")
text = path.read_text(encoding="utf-8")

old = """@require_POST
def api_vision_3d_camera_test(request):
    try:
        from apps.dm_camera.services import DMCameraService
        status = DMCameraService().get_status()
        return _api3d_success({
            'online': bool(status.get('connected') or status.get('streaming')),
            'status': status,
        })
    except Exception as exc:  # noqa: BLE001
        return _api3d_success({
            'online': False,
            'status': {'error': str(exc)},
        })
"""

new = """@require_POST
def api_vision_3d_camera_test(request):
    try:
        from apps.rvc_camera.services import RvcCameraService
        status = RvcCameraService().get_status()
        return _api3d_success({
            'online': bool(status.get('connected') or status.get('streaming')),
            'status': status,
        })
    except Exception as exc:  # noqa: BLE001
        return _api3d_success({
            'online': False,
            'status': {'error': str(exc)},
        })
"""

assert text.count(old) == 1, "camera test view anchor not found"
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("vision/views.py patched OK")
