"""Four-ROI editing, depth diagnostics and validated XYZ teaching; no PLC I/O."""
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

from .algorithms.rack_dual_point import (TARGETS, image_roi, locate_2d, compare_2d_debug,
    locate, teach_reference, compensation, measurement_digest)
from .rack_dual_point_quality import cloud_forensics
from .rack_camera_points import teach_image_edges, camera_pointmap_measurement
from .models import RackLocationRecipe

SALT = 'rack-dual-point-image-v1'


def draft_config(width, height):
    """Editable 2D starting parameters, explicitly not validated process limits."""
    return {'algorithm': 'Projection', 'rois': [], 'imageSize': [width, height],
            'lineQuality': {'min_points': 6, 'ransac_px': 2, 'iterations': 200,
                            'min_inlier_ratio': .6, 'min_valid_ratio': .4,
                            'max_residual_px': 1.5, 'max_tilt_deg': 20},
            'intersectionBounds': {'P1': [0, 0, width-1, height-1], 'P2': [0, 0, width-1, height-1]},
            'minIntersectionSine': .2, 'compareAlgorithms': False, 'maxAlgorithmDifferencePx': None,
            'geometry': {}, 'forensics': {'regions': {}}, 'maxOffsetMm': None,
            'placementTransfer': {'verified': False, 'calibrationVersion': '', 'evidence': '',
                'inputFrame': 'robot_base', 'outputFrame': '', 'layers': {
                    str(i): {'k_layer': None, 'axisMap': None, 'maxPlacementOffsetMm': None} for i in (1, 2)}},
            'acceptance': {'verified': False, 'evidence': '', 'minFrames': 30,
                'exploratoryThreeSigmaMm': [[.5, .5, .5], [.5, .5, .5]],
                'maxThreeSigmaMm': None, 'maxGrrPercentTolerance': None,
                'toleranceWidthMm': None, 'maxFailureRate': None},
            'validationStatus': '2d_draft_not_production_validated'}


def resolved_edge_config(image, config):
    if any(r.get('edgeSelection') == 'auto' for r in config.get('rois', [])) or (
        config.get('validationStatus') == '2d_draft_not_production_validated'
        and any(not r.get('imageDirection') for r in config.get('rois', []))
    ):
        return teach_image_edges(image, config)
    return config


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
            raise ValueError('当前数据包缺少 2D 原图，不能用深度伪彩图测边')
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
    # This image is only used for 2D diagnostics; it does not establish 3D sync.
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
        cloud_mode = data.get('localization_mode') == 'cloud_match'
        config_key = 'cloud_match_config' if cloud_mode else 'dual_point'
        config = (recipe.roi_config or {}).get(config_key) if recipe else None
        if cloud_mode and not config and recipe:
            config = (recipe.roi_config or {}).get('dual_point')
        reference = (recipe.roi_config or {}).get('cloud_match_reference' if cloud_mode else 'dual_point_camera_reference') if recipe else None
        if cloud_mode and reference:
            reference = {'measurement': reference['measurement']}
        edge_hint = ''
        if config and not cloud_mode:
            try:
                config = resolved_edge_config(image, config)
            except ValueError as exc:
                # Keep the canvas available so a bad ROI can be redrawn.
                edge_hint = str(exc)
        return JsonResponse({'success': True, 'image_token': token, 'width': w, 'height': h,
                             'image_url': reverse('vision:rack_dual_point_image')+'?token='+token,
                             'depth_preview_url': reverse('vision:rack_dual_point_depth')+'?token='+cloud_token,
                             'cloud_token': cloud_token,
                             'pointcloud_name': cloud_path.parent.name+'/'+cloud_path.name,
                             'config': config or draft_config(w, h), 'recipe_id': recipe.pk if recipe else None,
                             'reference': reference,
                             'three_d_status': edge_hint or '原图与 ROI 已准备；点击「开始计算」获取 P1、P2 的 XYZ'})
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
    if len(rois) != 4 or {r['target'] for r in rois} != set(TARGETS):
        raise ValueError('请画满四个 ROI：P1 横杆/立柱、P2 横杆/立柱')
    for roi in rois:
        image_roi(roi, shape)
    # Verify finite JSON before persisting any draft.
    json.dumps(config, allow_nan=False)


@require_POST
def auto_rois(request):
    try:
        from .rack_auto_roi import auto_roi_config
        data = json.loads(request.body or '{}')
        image = _read_image(_signed_image(data['image_token']))
        recipe = RackLocationRecipe.objects.get(pk=data['recipe_id']) if data.get('recipe_id') else None
        saved = (recipe.roi_config or {}).get('dual_point') if recipe else None
        config, result = auto_roi_config(image, data.get('config'), saved)
        return JsonResponse({'success': True, 'config': config, 'result': result,
                             'three_d_success': False, 'plc_publish_allowed': False})
    except (OSError, ValueError, KeyError, TypeError, OverflowError, cv2.error,
            signing.BadSignature, RackLocationRecipe.DoesNotExist) as exc:
        return error_response(exc)


@require_POST
def test_2d(request):
    try:
        data = json.loads(request.body or '{}')
        image = _read_image(_signed_image(data['image_token']))
        config = data['config']
        validate_config(config, image.shape)
        config = resolved_edge_config(image, config)
        result = locate_2d(image, config, strict_support=False)
        if config.get('compareAlgorithms'):
            result['comparison'] = compare_2d_debug(image, config, result)
        return JsonResponse({'success': True, 'two_d_success': True, 'three_d_success': False,
                             'compensation_valid': False, 'plc_publish_allowed': False, 'result': result,
                             'message': '二维检测通过；三维参考点尚未验证，不能保存 XYZ 示教或发布补偿'})
    except (OSError, ValueError, KeyError, TypeError, OverflowError, cv2.error, signing.BadSignature) as exc:
        return error_response(exc)


@require_POST
def save_config(request):
    try:
        data = json.loads(request.body or '{}')
        image = _read_image(_signed_image(data['image_token']))
        config = data['config']
        validate_config(config, image.shape)
        cloud_mode = data.get('localization_mode') == 'cloud_match'
        if not cloud_mode:
            config = resolved_edge_config(image, config)
        with transaction.atomic():
            recipe = RackLocationRecipe.objects.select_for_update().get(pk=data['recipe_id'])
            # Patch one namespace only. Existing three-plane/recipe data is preserved.
            recipe.roi_config = {**(recipe.roi_config or {}),
                                 ('cloud_match_config' if cloud_mode else 'dual_point'): config}
            reference = recipe.roi_config.get('dual_point_camera_reference')
            if reference and not cloud_mode:
                # ROI changes affect the next measurement, not saved standard XYZ.
                reference.pop('invalidated_reason', None)
            recipe.save(update_fields=['roi_config'])
        return JsonResponse({'success': True, 'recipe_id': recipe.pk, 'config': config,
                             'message': '四 ROI 配置已保存；可继续使用已有标准模板计算偏差'})
    except (OSError, ValueError, KeyError, TypeError, signing.BadSignature, RackLocationRecipe.DoesNotExist) as exc:
        return error_response(exc)


def _frame_package(data):
    """Read original units/contracts, never infer calibration from legacy defaults."""
    from .rack_dual_point_offline import load_package
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
            'metadata': {'source': source, 'frame_id': path.stem,
                         'camera': {'pointcloud_unit': units.get('unit')}},
            'hand_eye': None, 'robot_pose': None, 'pixel_index_map': None}


@require_POST
def forensics(request):
    try:
        data = json.loads(request.body or '{}')
        package = _frame_package(data)
        config = data.get('config') or {}
        report = cloud_forensics(package['cloud'], package['metadata'].get('camera', {}).get('pointcloud_unit'),
                                 config.get('forensics', {}).get('regions'))
        return JsonResponse({'success': True, 'report': report, 'plc_publish_allowed': False})
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        return error_response(exc)


@require_POST
def evaluate(request):
    """Run the independent 3D gate; successful diagnostics still never publish PLC."""
    try:
        data = json.loads(request.body or '{}')
        path = _signed_image(data['image_token'])
        if path.resolve() != _original_image(data).resolve():
            raise ValueError('当前点云与已加载原图来源不同，请重新载入')
        image = _read_image(path)
        config = data['config']
        validate_config(config, image.shape)
        config = resolved_edge_config(image, config)
        if data.get('cloud_token'):
            cloud_record = signing.loads(data['cloud_token'], salt=SALT+'-depth', max_age=3600)
            cloud_path = _cloud_path(data)
            cloud_stat = cloud_path.stat()
            if (cloud_path.resolve() != Path(cloud_record['path']).resolve() or
                cloud_stat.st_mtime_ns != cloud_record['mtime'] or cloud_stat.st_size != cloud_record['size']):
                raise ValueError('点云与已载入原图的采集帧不一致，请重新载入')
        package = _frame_package(data)
        report = cloud_forensics(package['cloud'], package['metadata'].get('camera', {}).get('pointcloud_unit'),
                                 config.get('forensics', {}).get('regions'))
        camera_only = data.get('coordinate_system') == 'camera'
        if camera_only and not package['metadata'].get('dual_point_contract') and package['metadata'].get('source') == 'rvc_camera':
            result = camera_pointmap_measurement(image, package['cloud'], config, package['metadata'])
        else:
            result = locate(image, package['cloud'], config, package['metadata'],
                            package['hand_eye'], package['robot_pose'], package['pixel_index_map'], camera_only=camera_only)
        recipe = RackLocationRecipe.objects.get(pk=data['recipe_id']) if data.get('recipe_id') else None
        reference_key = 'dual_point_camera_reference' if camera_only else 'dual_point_reference'
        reference = (recipe.roi_config or {}).get(reference_key) if recipe else None
        offset = compensation(result, reference, config) if reference and not camera_only else {
            'success': False, 'compensation_valid': False, 'plc_publish_allowed': False,
            'errorMessage': '相机坐标测量不计算机器人补偿' if camera_only else '尚未保存通过三维校验的 XYZ 示教'}
        from .rack_robot_points import evaluate_robot_points
        robot_result = evaluate_robot_points(result, reference) if camera_only else None
        token = signing.dumps({'result': result, 'recipe_id': recipe.pk,
            'camera_config': config if camera_only else None,
            'saved_config_digest': measurement_digest((recipe.roi_config or {}).get('dual_point') or {})}, salt=SALT+'-teach', compress=True) if result['success'] and recipe else None
        # Auto-save result record (no image) so every compute is visible in tasks / hand-eye pages.
        _save_evaluate_record(recipe, result, robot_result, camera_only)
        return JsonResponse({'success': True, 'result': result, 'compensation': offset, 'forensics': report,
            'reference': reference, 'robot_result': robot_result, 'teach_token': token, 'plc_publish_allowed': False})
    except (OSError, ValueError, KeyError, TypeError, OverflowError, cv2.error,
            signing.BadSignature, RackLocationRecipe.DoesNotExist) as exc:
        return error_response(exc)


def _save_evaluate_record(recipe, result, robot_result, camera_only):
    """Persist a VisionTask + RackLocationResult after each evaluate(), without any image."""
    try:
        from django.db import transaction as _tx
        from apps.core.constants import ResultStatus, VisionTaskType
        from .models import VisionTask, RackLocationResult
        from decimal import Decimal

        is_success = bool(result.get('success'))
        with _tx.atomic():
            task = VisionTask.objects.create(
                task_type=VisionTaskType.RACK_LOCATING,
                status=ResultStatus.SUCCESS if is_success else ResultStatus.FAILED,
                error_message=result.get('errorMessage', ''),
            )
            points = {p['name']: p for p in (result.get('points') or [])}
            p1 = points.get('P1', {})
            p2 = points.get('P2', {})
            dec = lambda v: Decimal(str(round(float(v), 3))) if v is not None and str(v) != 'None' else Decimal('0')
            p1_xyz = p1.get('xyz') or [0, 0, 0]
            robot_offsets = (robot_result or {}).get('offsets') or [[0, 0, 0], [0, 0, 0]]
            record = RackLocationResult.objects.create(
                vision_task=task,
                recipe=recipe,
                side=recipe.rack_side if recipe else 'BOTH',
                position_no=recipe.position_no if recipe else 1,
                layer_no=recipe.layer_no if recipe else 1,
                actual_x=dec(p1_xyz[0] if len(p1_xyz) > 0 else 0),
                actual_y=dec(p1_xyz[1] if len(p1_xyz) > 1 else 0),
                actual_z=dec(p1_xyz[2] if len(p1_xyz) > 2 else 0),
                offset_x=dec(robot_offsets[0][0] if robot_result and robot_result.get('success') else 0),
                offset_y=dec(robot_offsets[0][1] if robot_result and robot_result.get('success') else 0),
                offset_z=dec(robot_offsets[0][2] if robot_result and robot_result.get('success') else 0),
                confidence=dec(result.get('confidence', 1.0) if is_success else 0),
                is_success=is_success,
                error_code=result.get('errorCode', ''),
                error_message=result.get('errorMessage', ''),
                result_data={
                    'source': 'dual_point_evaluate',
                    'camera_only': camera_only,
                    'result': result,
                    'robot_result': robot_result,
                },
            )
        # Keep only the latest 3 records per recipe+layer (reuse the existing cleanup).
        if recipe is not None:
            from .rack_3d.services import RackPositioningService
            RackPositioningService._cleanup_old_rack_results(recipe.id, record.layer_no)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('dual_point evaluate: failed to auto-save result record')


@require_POST
def teach(request):
    try:
        data = json.loads(request.body or '{}')
        signed = signing.loads(data['teach_token'], salt=SALT+'-teach', max_age=3600)
        if str(signed['recipe_id']) != str(data['recipe_id']):
            raise ValueError('示教结果不属于当前配方')
        result = signed['result']
        with transaction.atomic():
            recipe = RackLocationRecipe.objects.select_for_update().get(pk=data['recipe_id'])
            config = (recipe.roi_config or {}).get('dual_point')
            camera_config = signed.get('camera_config')
            if result.get('coordinateSystem') == 'camera' and camera_config is not None:
                if measurement_digest(camera_config) != result['config_digest']:
                    raise ValueError('计算结果与 ROI 配置不一致，请重新计算')
                current_digest = measurement_digest(config or {})
                if current_digest not in (signed['saved_config_digest'], result['config_digest']):
                    raise ValueError('此配方已被其他操作修改，请重新载入并计算后保存模板')
                # Persist the exact ROI/algorithm configuration used for these XYZ values.
                recipe.roi_config = {**(recipe.roi_config or {}), 'dual_point': camera_config}
            elif not config or measurement_digest(config) != result['config_digest']:
                raise ValueError('请先保存当前定位配置并重新校验三维，再保存 XYZ 示教')
            reference = teach_reference(result)
            reference_key = 'dual_point_camera_reference' if result.get('coordinateSystem') == 'camera' else 'dual_point_reference'
            recipe.roi_config = {**recipe.roi_config, reference_key: reference}
            recipe.save(update_fields=['roi_config'])
        from .rack_robot_points import robot_point_difference
        context = result.get('robot_transform_context')
        robot_result = robot_point_difference(result, reference, context) if context else None
        return JsonResponse({'success': True, 'reference': reference, 'robot_result': robot_result, 'config': recipe.roi_config.get('dual_point'), 'plc_publish_allowed': False,
                             'message': '相机坐标标准模板已保存。' if result.get('coordinateSystem') == 'camera' else '双点 XYZ 示教已保存。请使用新的采集帧校验三维并计算偏移。'})
    except (OSError, ValueError, KeyError, TypeError, signing.BadSignature, RackLocationRecipe.DoesNotExist) as exc:
        return error_response(exc)


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

        if record.result_data.get('source') != 'dual_point_evaluate':
            raise ValueError('该记录不是双交点定位结果，无法重新计算')

        stored_result = record.result_data.get('result') or {}
        if not stored_result.get('success'):
            raise ValueError('原始计算未成功，没有有效的相机坐标可以转换')

        reference_key = 'dual_point_camera_reference'
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
            for i, name in enumerate(('P1', 'P2')):
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
                recipe.roi_config = {**(recipe.roi_config or {}), 'cloud_match_reference': reference,
                                     'cloud_match_config': config}
                recipe.save(update_fields=['roi_config'])
            result = reference['measurement']
        else:
            reference = (recipe.roi_config or {}).get('cloud_match_reference')
            result = match_template(package['cloud'], package['metadata'], reference)
        result = add_display_pixels(result, package['cloud'], package['metadata'])
        robot = evaluate_robot_points(result, reference) if result['success'] else None
        # Experimental results stay separate from legacy edge-result history.
        return JsonResponse({'success': True, 'result': result,
            'reference': {'measurement': reference['measurement']}, 'robot_result': robot,
            'config': reference['config'], 'plc_publish_allowed': False})
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError,
            signing.BadSignature, RackLocationRecipe.DoesNotExist) as exc:
        return error_response(exc)
