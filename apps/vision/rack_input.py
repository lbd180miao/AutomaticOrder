"""Validate the actual frame and pixel ROIs before rack measurement."""
import hashlib
import math

import numpy as np
from django.conf import settings


def capture_input(provider, recipe, position_no, layer_no):
    """A live capture failure must not become a measurement of a demo scene."""
    try:
        frame = provider.capture(recipe, position_no, layer_no)
    except Exception as exc:
        raise ValueError(f'相机采集失败：{exc}；未替换为模拟或历史点云，请检查相机后重试') from exc
    source = str(frame.get('source') or '')
    forced_demo = (source == 'sample_forced'
                   and getattr(settings, 'VISION_RACK_LOCATION_FORCE_SAMPLE', False))
    if source not in ('rvc_camera', 'dm_camera') and not forced_demo:
        reason = frame.get('fallback_reason') or source or '未提供真实相机数据来源'
        raise ValueError(f'未取得实时相机点云：{reason}；已停止计算，离线数据请通过“加载离线数据”选择')
    cloud = frame.get('organized_pointcloud')
    if cloud is None and forced_demo:
        from .rack_location import build_sample_pointcloud
        key = f'{getattr(recipe, "pk", None)}:{layer_no}'.encode('utf-8')
        seed = int.from_bytes(hashlib.sha256(key).digest()[:4], 'little')
        cloud = build_sample_pointcloud(layer_count=recipe.layer_count or 3,
                                       seed=seed, local_template_geometry=True)
    if cloud is None:
        raise ValueError('相机未返回组织化点云，请检查采集模式；未替换为模拟数据')
    cloud = np.asarray(cloud, dtype=np.float64)
    if cloud.ndim != 3 or cloud.shape[2] != 3 or min(cloud.shape[:2]) < 2:
        raise ValueError('相机点云必须是 H×W×3，且宽高不能小于 2')
    valid = np.isfinite(cloud).all(axis=2) & (np.abs(cloud[:, :, 2]) > 1e-9)
    if np.count_nonzero(valid) < 50:
        raise ValueError('相机点云有效点不足 50，请重新采集')
    return frame, cloud


def plane_roi(raw, width, height, label):
    """Do not clamp a ROI from another resolution into a one-pixel strip."""
    try:
        x, y = float(raw['x']), float(raw['y'])
        w, h = float(raw.get('w', raw.get('width'))), float(raw.get('h', raw.get('height')))
        if not np.isfinite([x, y, w, h]).all():
            raise ValueError
        x0, y0 = math.floor(x), math.floor(y)
        x1, y1 = math.ceil(x + w), math.ceil(y + h)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'{label}: ROI 参数无效，需要有限的 x/y/w/h') from exc
    if w < 2 or h < 2:
        raise ValueError(f'{label}: 平面 ROI 宽高至少 2 像素，单行或单列不能可靠拟合平面')
    if x0 < 0 or y0 < 0 or x1 > width or y1 > height:
        raise ValueError(f'{label}: ROI 超出当前点云 {width}×{height}，数据分辨率或来源可能已改变，请加载对应点云或重新框选；未自动裁剪 ROI')
    return {'x': x0, 'y': y0, 'w': x1-x0, 'h': y1-y0}


def cloud_identity(cloud):
    """Hash persisted float32 geometry and shape, independent of fit parameters."""
    array = np.array(cloud, dtype='<f4', order='C', copy=True)
    array[np.isnan(array)] = np.nan  # canonical NaN representation
    digest = hashlib.sha256(np.asarray(array.shape, dtype='<i8').tobytes())
    digest.update(array.tobytes())
    return {'pointcloud_sha256': digest.hexdigest(),
            'image_width': int(array.shape[1]) if array.ndim == 3 else None,
            'image_height': int(array.shape[0]) if array.ndim == 3 else None,
            'point_count': int(array.size // 3)}
