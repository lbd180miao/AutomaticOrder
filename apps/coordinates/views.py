import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .services import CoordinateWorkbenchError, CoordinateWorkbenchService


logger = logging.getLogger(__name__)


def workbench(request):
    return render(request, 'coordinates/workbench.html', {
        'pose_rotation_keys': ('rx', 'ry', 'rz'),
    })


@require_GET
def api_workbench(request):
    try:
        data = CoordinateWorkbenchService().get_workbench(request.GET.get('layer_no', 1))
        return _success(data)
    except Exception as exc:
        return _failure(exc)


@require_POST
def api_preview(request):
    try:
        data = CoordinateWorkbenchService().preview(_json_body(request))
        return _success(data)
    except Exception as exc:
        return _failure(exc)


@require_POST
def api_save(request):
    try:
        service = CoordinateWorkbenchService()
        saved = service.save(_json_body(request))
        return _success(service.preview(saved))
    except Exception as exc:
        return _failure(exc)


@require_POST
def api_transform_roi(request):
    try:
        payload = _json_body(request)
        data = CoordinateWorkbenchService().transform_camera_roi(
            layer_no=payload.get('layer_no'),
            camera_roi=payload.get('camera_roi'),
            recipe_id=payload.get('recipe_id'),
        )
        return _success(data)
    except Exception as exc:
        return _failure(exc)


def _json_body(request):
    try:
        value = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinateWorkbenchError('INVALID_JSON', '请求体不是有效 JSON') from exc
    if not isinstance(value, dict):
        raise CoordinateWorkbenchError('INVALID_JSON', '请求体必须是 JSON 对象')
    return value


def _success(data):
    return JsonResponse({'success': True, 'data': data, 'error': None})


def _failure(exc):
    if isinstance(exc, CoordinateWorkbenchError):
        return JsonResponse({
            'success': False,
            'data': None,
            'error': {
                'code': exc.code, 'message': exc.message, 'fields': exc.fields,
            },
        }, status=exc.status)
    logger.exception('坐标模块请求失败', exc_info=exc)
    return JsonResponse({
        'success': False,
        'data': None,
        'error': {'code': 'INTERNAL_ERROR', 'message': '坐标模块内部错误', 'fields': {}},
    }, status=500)


# ─────────────────────────────────────────────────────────
# REAL 模式（以下为新增，不影响上方任何已有接口）
# ─────────────────────────────────────────────────────────

_REAL_CACHE_KEY = 'coordinates_real_last_pointcloud'
_REAL_CACHE_TTL = 86400  # 24 小时


def workbench_real(request):
    """REAL 实机模式工作台页面。"""
    return render(request, 'coordinates/workbench_real.html', {
        'pose_rotation_keys': ('rx', 'ry', 'rz'),
    })


@require_POST
def api_capture_real(request):
    """
    调用真实 3D 相机采集点云，使用前端传入的手眼矩阵和机器人位姿做坐标转换。

    请求体（JSON）：
      layer_no       : 层号 1/2/3
      hand_eye_matrix: 4×4 列表
      robot_pose     : {x, y, z, rx, ry, rz}
      theoretical    : {x, y, z}
      roi            : {x_min, x_max, y_min, y_max, z_min, z_max}
    """
    import numpy as np
    from datetime import datetime as _dt
    from django.core.cache import cache

    from apps.vision.coordinate_transform import CoordinateTransformService
    from apps.vision.rack_3d.providers import RealDepthCameraProvider
    from apps.vision.rack_3d.processors import PointCloudProcessor

    try:
        payload = _json_body(request)

        # ── 解析前端输入 ──────────────────────────────────────
        svc = CoordinateWorkbenchService
        layer_no  = svc._layer(payload.get('layer_no', 1))
        he_matrix = svc._matrix(payload.get('hand_eye_matrix'))
        pose      = svc._numbers(payload.get('robot_pose'), ('x', 'y', 'z', 'rx', 'ry', 'rz'))
        theoretical = svc._numbers(
            payload.get('theoretical', {'x': 0.0, 'y': 0.0, 'z': 0.0}),
            ('x', 'y', 'z')
        )
        roi = svc._numbers(
            payload.get('roi'), ('x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max')
        )

        # ── 采集真实点云（直接绕过 RACK_3D_POSITIONING_MODE）──
        camera_provider = RealDepthCameraProvider()
        pc_data = camera_provider.capture_pointcloud(layer_no=layer_no)

        # ── 坐标转换 ──────────────────────────────────────────
        ts = CoordinateTransformService()
        T_base_flange = ts.pose_to_matrix(
            pose['x'], pose['y'], pose['z'],
            pose['rx'], pose['ry'], pose['rz'],
        )
        processor = PointCloudProcessor()
        base_pts = processor.transform_to_robot_coords(pc_data['data'], he_matrix, T_base_flange)

        # 保存原始相机点（转换前，N×3）
        raw_pts = np.asarray(pc_data['data'], dtype=np.float64)
        if raw_pts.ndim == 3:
            raw_pts = raw_pts.reshape(-1, 3)
        valid = np.isfinite(raw_pts).all(axis=1) & (np.abs(raw_pts).sum(axis=1) > 1e-6)
        raw_pts = raw_pts[valid]

        # ── ROI 裁剪 ─────────────────────────────────────────
        mask = (
            (base_pts[:, 0] >= roi['x_min']) & (base_pts[:, 0] <= roi['x_max'])
            & (base_pts[:, 1] >= roi['y_min']) & (base_pts[:, 1] <= roi['y_max'])
            & (base_pts[:, 2] >= roi['z_min']) & (base_pts[:, 2] <= roi['z_max'])
        )
        roi_pts = base_pts[mask]

        # ── 计算实际坐标与偏差 ────────────────────────────────
        if len(roi_pts) > 0:
            actual = {a: float(np.median(roi_pts[:, i])) for i, a in enumerate(('x', 'y', 'z'))}
        else:
            actual = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        offset = {a: actual[a] - theoretical[a] for a in ('x', 'y', 'z')}

        # ── 存入 Django Cache（供下次页面加载使用）────────────
        LIMIT = 1500

        def _display(pts):
            pts = np.asarray(pts, dtype=np.float64)
            if len(pts) > LIMIT:
                idx = np.linspace(0, len(pts) - 1, LIMIT, dtype=int)
                pts = pts[idx]
            return pts.round(3).tolist()

        def _ranges(pts):
            pts = np.asarray(pts, dtype=np.float64)
            if len(pts) == 0:
                return {f'{a}_{e}': 0.0 for a in 'xyz' for e in ('min', 'max')}
            lo, hi = pts.min(axis=0), pts.max(axis=0)
            return {
                f'{a}_{e}': float(v)
                for a, low, high in zip('xyz', lo, hi)
                for e, v in (('min', low), ('max', high))
            }

        captured_at = _dt.now().strftime('%Y-%m-%d %H:%M:%S')

        result_payload = {
            'source': 'REAL',
            'captured_at': captured_at,
            'frame_index': pc_data.get('frame_index'),
            'camera_points':  _display(raw_pts),
            'base_points':    _display(base_pts),
            'roi_points':     _display(roi_pts),
            'point_counts': {
                'camera': int(len(raw_pts)),
                'base':   int(len(base_pts)),
                'roi':    int(len(roi_pts)),
            },
            'coordinate_ranges': {
                'camera': _ranges(raw_pts),
                'base':   _ranges(base_pts),
                'roi':    _ranges(roi_pts) if len(roi_pts) else _ranges(base_pts),
            },
            'actual': actual,
            'theoretical': theoretical,
            'offset': offset,
            'config': {
                'layer_no': layer_no,
                'hand_eye_matrix': he_matrix.tolist(),
                'robot_pose': pose,
                'theoretical': theoretical,
                'roi': roi,
            },
        }

        # 存缓存（不序列化 numpy，全部已是 list/dict）
        cache.set(_REAL_CACHE_KEY, result_payload, timeout=_REAL_CACHE_TTL)

        return _success(result_payload)

    except CoordinateWorkbenchError:
        raise
    except Exception as exc:
        # 把底层相机异常包成友好消息
        msg = str(exc)
        if 'stream' in msg.lower() or 'connect' in msg.lower() or 'camera' in msg.lower():
            return JsonResponse({
                'success': False,
                'data': None,
                'error': {
                    'code': 'CAMERA_ERROR',
                    'message': f'相机采集失败：{msg}',
                    'fields': {},
                },
            }, status=503)
        return _failure(exc)


@require_GET
def api_real_last_capture(request):
    """返回最近一次 REAL 模式采集的结果（来自 Django Cache），供页面初始化使用。"""
    from django.core.cache import cache
    data = cache.get(_REAL_CACHE_KEY)
    if data is None:
        return _success(None)
    return _success(data)
