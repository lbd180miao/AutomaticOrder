"""Point-cloud template registration and ROI editing; no PLC I/O."""
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

import cv2
import numpy as np
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import FileResponse, JsonResponse, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .rack_cloud_roi import required_targets, image_roi, algorithm_keys
from .models import RackLocationRecipe

SALT = 'rack-dual-point-image-v1'


def draft_config(width, height):
    """Only pixel regions are needed to build a point-cloud template."""
    return {'algorithm': 'cloud_center', 'rois': [], 'imageSize': [width, height]}


def error_response(exc):
    return JsonResponse({'success': False, 'errorCode': getattr(exc, 'code', 'INVALID_INPUT'),
                         'stage': getattr(exc, 'stage', 'input'), 'errorMessage': str(exc)}, status=400)


def _media_file(relative):
    root = Path(settings.MEDIA_ROOT).resolve()
    path = (root/relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('图像/点云路径必须位于采集数据目录中')
    return path


def _original_image(data):
    source = str(data.get('source') or '')
    if source.startswith(('offline_package:', 'raw_package:')):
        from .offline_data_service import OfflineDataPackageService
        svc = OfflineDataPackageService()
        path = svc.get_2d_image(source.split(':', 1)[1])
        if path is None:
            raise ValueError('当前数据包缺少 2D 原图，无法显示 ROI 框选底图')
        return path.resolve()
    token = data.get('pointcloud_token')
    if not token:
        raise ValueError('请先采集或加载一帧数据')
    cloud_path = _media_file(token)
    sibling = cloud_path.with_name(cloud_path.stem+'_image2d.png')
    if sibling.is_file():
        return _media_file(str(sibling.relative_to(Path(settings.MEDIA_ROOT).resolve())))
    url = urlsplit(data.get('raw_rgb_image_url') or '')
    path = unquote(url.path)
    if url.scheme or url.netloc or not path.startswith(settings.MEDIA_URL):
        raise ValueError('当前帧没有可用的 2D 原图，请重新采集或加载含 image2d.png 的数据包')
    # The registration endpoint separately checks the image/cloud frame tokens.
    return _media_file(path[len(settings.MEDIA_URL):])


def _read_image(path):
    image = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('无法读取相机 2D 原图')
    return image


def _signed_image(token):
    payload = signing.loads(token, salt=SALT, max_age=3600)
    path = Path(payload['path'])
    stat = path.stat()
    if stat.st_mtime_ns != payload['mtime'] or stat.st_size != payload['size']:
        raise ValueError('图像内容已变化，请重新加载当前帧')
    return path


def _cloud_path(data):
    source = str(data.get('source') or '')
    if source.startswith(('offline_package:', 'raw_package:')):
        from .offline_data_service import OfflineDataPackageService
        path = OfflineDataPackageService()._package_dir(source.split(':', 1)[1])/'pointcloud.npy'
        if not path.is_file():
            raise ValueError('数据包缺少对应的 pointcloud.npy')
        return path
    return _media_file(data['pointcloud_token'])


@require_POST
def prepare(request):
    try:
        data = json.loads(request.body or '{}')
        path = _original_image(data)
        image = _read_image(path)
        h, w = image.shape[:2]
        stat = path.stat()
        token = signing.dumps({'path': str(path), 'mtime': stat.st_mtime_ns, 'size': stat.st_size}, salt=SALT)
        cloud_path = _cloud_path(data)
        cloud_stat = cloud_path.stat()
        cloud_token = signing.dumps({'path': str(cloud_path), 'mtime': cloud_stat.st_mtime_ns,
                                    'size': cloud_stat.st_size}, salt=SALT+'-depth')
        recipe = RackLocationRecipe.objects.get(pk=data['recipe_id']) if data.get('recipe_id') else None
        algorithm = data.get('algorithm', 'cloud_center')
        config_key, reference_key = algorithm_keys(algorithm)
        config = (recipe.roi_config or {}).get(config_key) if recipe else None
        reference = (recipe.roi_config or {}).get(reference_key) if recipe else None
        if not config:
            config = {**draft_config(w, h), 'algorithm': algorithm}
        if reference:
            reference = {'measurement': {**reference['measurement'],
                         'center_xyz': reference.get('center_xyz') or np.asarray(reference['points']).mean(axis=0).tolist()}}
        return JsonResponse({'success': True, 'image_token': token, 'width': w, 'height': h,
                             'image_url': reverse('vision:rack_dual_point_image')+'?token='+token,
                             'depth_preview_url': reverse('vision:rack_dual_point_depth')+'?token='+cloud_token,
                             'cloud_token': cloud_token,
                             'pointcloud_name': cloud_path.parent.name+'/'+cloud_path.name,
                             'config': config or draft_config(w, h), 'recipe_id': recipe.pk if recipe else None,
                             'reference': reference,
                             'three_d_status': '原图与 ROI 已准备；保存标准点云模板后点击「开始计算」'})
    except (OSError, ValueError, TypeError, KeyError, RackLocationRecipe.DoesNotExist) as exc:
        return error_response(exc)


@require_GET
def depth_preview(request):
    try:
        payload = signing.loads(request.GET.get('token', ''), salt=SALT+'-depth', max_age=3600)
        path = Path(payload['path'])
        stat = path.stat()
        if stat.st_mtime_ns != payload['mtime'] or stat.st_size != payload['size']:
            raise ValueError('点云内容已变化，请重新加载当前帧')
        cloud = np.load(path, allow_pickle=False)
        if cloud.ndim != 3 or cloud.shape[2] != 3:
            raise ValueError('伪彩图需要组织化点云 H×W×3')
        from .algorithms.image_io import pointcloud_to_preview
        preview = np.asarray(pointcloud_to_preview(cloud), dtype=np.uint8)
        ok, encoded = cv2.imencode('.png', preview)
        if not ok:
            raise ValueError('点云伪彩图生成失败')
        return HttpResponse(encoded.tobytes(), content_type='image/png')
    except (OSError, ValueError, KeyError, TypeError, cv2.error, signing.BadSignature) as exc:
        return error_response(exc)


@require_GET
def original_image(request):
    try:
        return FileResponse(_signed_image(request.GET.get('token', '')).open('rb'), content_type='image/png')
    except (OSError, ValueError, KeyError, signing.BadSignature) as exc:
        return error_response(exc)


def validate_config(config, shape):
    if config.get('imageSize') != [shape[1], shape[0]]:
        raise ValueError('ROI 配置分辨率与当前原图不同，请重新框选或加载对应原图')
    rois = config['rois']
    targets = required_targets(config)
    if len(rois) != len(targets) or {r['target'] for r in rois} != set(targets):
        raise ValueError(f'请完成 {len(targets)} 个 ROI，覆盖所选算法要求的参考区域')
    for roi in rois:
        image_roi(roi, shape)
    # Verify finite JSON before persisting any draft.
    json.dumps(config, allow_nan=False)


@require_POST
def save_config(request):
    try:
        data = json.loads(request.body or '{}')
        image = _read_image(_signed_image(data['image_token']))
        config = data['config']
        validate_config(config, image.shape)
        config_key, reference_key = algorithm_keys(config.get('algorithm', 'cloud_center'))
        with transaction.atomic():
            recipe = RackLocationRecipe.objects.select_for_update().get(pk=data['recipe_id'])
            recipe.roi_config = {**(recipe.roi_config or {}), config_key: config}
            recipe.save(update_fields=['roi_config'])
        return JsonResponse({'success': True, 'recipe_id': recipe.pk, 'config': config,
                             'message': 'ROI 配置已保存；若修改了区域或层数，请重新保存点云标准模板'})
    except (OSError, ValueError, KeyError, TypeError, signing.BadSignature, RackLocationRecipe.DoesNotExist) as exc:
        return error_response(exc)


def _frame_package(data):
    """Read original units/contracts, never infer calibration from legacy defaults."""
    from .rack_cloud_package import load_package
    source = str(data.get('source') or '')
    if source.startswith(('offline_package:', 'raw_package:')):
        from .offline_data_service import OfflineDataPackageService
        directory = OfflineDataPackageService()._package_dir(source.split(':', 1)[1])
        if (directory/'pointcloud.npy').is_file():
            return load_package(directory)
    path = _media_file(data['pointcloud_token'])
    marker = path.with_suffix('.units.json')
    units = json.loads(marker.read_text(encoding='utf-8-sig')) if marker.is_file() else {}
    return {'cloud': np.load(path, allow_pickle=False), 'image': None, 'config': {},
            'metadata': {**units.get('capture_metadata', {}), 'source': units.get('capture_metadata', {}).get('source', source),
                         'frame_id': path.stem, 'camera': {**units.get('capture_metadata', {}).get('camera', {}),
                                                          'pointcloud_unit': units.get('unit')}},
            'hand_eye': None, 'robot_pose': None, 'pixel_index_map': None}


@require_POST
def recompute_robot_deviation(request):
    """Re-compute robot-base deviation for a saved dual_point_evaluate RackLocationResult.

    Uses the camera-coordinate P1/P2 points already stored in result_data plus the
    currently active hand-eye calibration (T_flange_camera + T_base_flange).
    No image or point cloud is needed.
    """
    try:
        from .models import RackLocationResult
        from .rack_robot_points import workspace_context, robot_point_difference

        data = json.loads(request.body or '{}')
        result_id = int(data['result_id'])
        record = RackLocationResult.objects.get(pk=result_id)

        if record.result_data.get('source') not in ('dual_point_evaluate', 'cloud_match'):
            raise ValueError('该记录不是双交点定位结果，无法重新计算')

        stored_result = record.result_data.get('result') or {}
        if not stored_result.get('success'):
            raise ValueError('原始计算未成功，没有有效的相机坐标可以转换')

        reference_key = ('cloud_center_reference' if record.result_data.get('algorithm') == 'cloud_center'
                         else 'cloud_match_reference' if record.result_data.get('source') == 'cloud_match'
                         else 'dual_point_camera_reference')
        recipe = record.recipe
        reference = (recipe.roi_config or {}).get(reference_key) if recipe else None
        if not reference:
            raise ValueError('配方尚未保存标准模板，请先在工作台执行「保存为标准模板」')

        context = workspace_context()
        robot_result = robot_point_difference(stored_result, reference, context)

        fmt3 = lambda v: round(float(v), 3) if isinstance(v, (int, float)) else None
        rows = []
        if robot_result.get('success'):
            offsets = robot_result.get('offsets') or []
            standard = robot_result.get('standard') or []
            current_pts = robot_result.get('current') or []
            for i, name in enumerate(('P1', 'P2')[:len(offsets)]):
                rows.append({
                    'name': name,
                    'standard': [fmt3(v) for v in standard[i]] if i < len(standard) else None,
                    'current':  [fmt3(v) for v in current_pts[i]] if i < len(current_pts) else None,
                    'offset':   [fmt3(v) for v in offsets[i]] if i < len(offsets) else None,
                })

        return JsonResponse({
            'success': True,
            'robot_result': robot_result,
            'rows': rows,
            'calibration_name': context.get('calibration_name', ''),
        })
    except (ValueError, KeyError, TypeError) as exc:
        return error_response(exc)
    except Exception as exc:
        from .models import RackLocationResult
        if isinstance(exc, RackLocationResult.DoesNotExist):
            return error_response(ValueError('记录不存在'))
        return error_response(exc)


@require_POST
def cloud_match(request):
    """Explicit experimental registration/template actions, isolated from edge templates."""
    try:
        from .rack_cloud_match import build_template, match_template, add_display_pixels
        from .rack_robot_points import evaluate_robot_points, workspace_context
        data = json.loads(request.body or '{}')
        action = data.get('action', 'evaluate')
        if action not in ('evaluate', 'save_template'):
            raise ValueError('未知点云匹配操作')
        image_path = _signed_image(data['image_token'])
        if image_path.resolve() != _original_image(data).resolve():
            raise ValueError('原图与点云来源不一致，请重新载入')
        record = signing.loads(data['cloud_token'], salt=SALT+'-depth', max_age=3600)
        cloud_path = _cloud_path(data)
        stat = cloud_path.stat()
        if (cloud_path.resolve() != Path(record['path']).resolve() or
                stat.st_mtime_ns != record['mtime'] or stat.st_size != record['size']):
            raise ValueError('点云采集帧已变化，请重新载入')
        package = _frame_package(data)
        image = _read_image(image_path)
        if package['cloud'].shape[:2] != image.shape[:2]:
            raise ValueError('原图与点云尺寸不一致')
        recipe = RackLocationRecipe.objects.get(pk=data['recipe_id'])
        algorithm = (data.get('config') or {}).get('algorithm', 'cloud_center')
        config_key, reference_key = algorithm_keys(algorithm)
        if action == 'save_template':
            config = data['config']
            validate_config(config, image.shape)
            reference = build_template(package['cloud'], config, package['metadata'])
            try:
                reference['measurement']['robot_transform_context'] = workspace_context()
            except ValueError:
                pass
            with transaction.atomic():
                recipe = RackLocationRecipe.objects.select_for_update().get(pk=recipe.pk)
                recipe.roi_config = {**(recipe.roi_config or {}), reference_key: reference,
                                     config_key: config}
                recipe.save(update_fields=['roi_config'])
            result = reference['measurement']
        else:
            reference = (recipe.roi_config or {}).get(reference_key)
            config = data.get('config') or (recipe.roi_config or {}).get(config_key) or {}
            if reference and required_targets(config) != required_targets(reference['config']):
                raise ValueError('料架层数与标准模板不同，请重新保存点云标准模板')
            if reference and config != reference['config']:
                raise ValueError('ROI 已变化，请重新保存当前算法的点云标准模板')
            from .rack_cloud_service import evaluate_cloud
            from django.conf import settings
            media_root = Path(settings.MEDIA_ROOT).resolve()
            history_token = str(cloud_path.resolve().relative_to(media_root)) if cloud_path.resolve().is_relative_to(media_root) else ''
            payload = evaluate_cloud(recipe, package['cloud'], package['metadata'],
                layer_no=int(data.get('layer_no') or 1), token=history_token,
                save_record=True, algorithm=algorithm, camera_image=image)
            return JsonResponse({'success': True, 'result': payload['result'],
                'reference': payload['reference'], 'robot_result': payload['robot_result'],
                'config': reference['config'], 'plc_publish_allowed': False,
                'result_id': payload['result_id'], 'task_id': payload['task_id']})
        result = add_display_pixels(result, package['cloud'], package['metadata'])
        robot = evaluate_robot_points(result, reference) if result['success'] else None
        # Experimental results stay separate from legacy edge-result history.
        return JsonResponse({'success': True, 'result': result,
            'reference': {'measurement': reference['measurement']}, 'robot_result': robot,
            'config': reference['config'], 'plc_publish_allowed': False})
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError,
            signing.BadSignature, RackLocationRecipe.DoesNotExist) as exc:
        return error_response(exc)
