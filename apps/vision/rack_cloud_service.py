"""Shared point-cloud registration for workbench, offline and production entry points."""
from decimal import Decimal
from time import perf_counter

from django.db import transaction
from django.utils import timezone

from apps.core.constants import ResultStatus, VisionTaskType
from .models import RackLocationResult, VisionTask
from .rack_cloud_roi import required_targets, algorithm_keys
from .rack_robot_points import evaluate_robot_points


def evaluate_cloud(recipe, cloud, metadata, *, layer_no=1, token='', save_record=False,
                   product=None, rack=None, algorithm='rivet', camera_image=None, task=None):
    config_key, reference_key = algorithm_keys(algorithm)
    reference = (recipe.roi_config or {}).get(reference_key)
    config = (recipe.roi_config or {}).get(config_key) or {}
    if reference and required_targets(config) != required_targets(reference['config']):
        raise ValueError('料架层数与标准模板不同，请重新保存点云标准模板')
    if reference and config != reference['config']:
        raise ValueError('ROI 已变化，请重新保存当前算法的点云标准模板')
    if config.get('algorithm') != 'rivet':
        raise ValueError('料架定位已改为三铆钉算法，请重新框选并保存铆钉标准模板')
    from .rack_rivet import match_template as match_rivets, VERSION as rivet_version
    if camera_image is None and token:
        from pathlib import Path
        from django.conf import settings
        from .rack_dual_point_views import _read_image
        root = Path(settings.MEDIA_ROOT).resolve()
        raw = (root / token).resolve()
        if not raw.is_relative_to(root):
            raise ValueError('采集路径不在数据目录内')
        camera_image = _read_image(raw.with_name(raw.stem + '_image2d.png'))
    started = perf_counter()
    result = match_rivets(cloud, metadata, reference, camera_image)
    matched = perf_counter()
    robot = evaluate_robot_points(result, reference) if result['success'] else None
    offsets = robot['offsets'] if robot and robot.get('success') else [[0, 0, 0], [0, 0, 0]]
    quality = result.get('registration') or {}
    payload = {
        'algorithm': 'rivet', 'algorithm_version': rivet_version, 'source': 'cloud_match', 'result': result,
        'reference': {'measurement': reference['measurement']}, 'robot_result': robot,
        'locate_ok': result['success'], 'is_success': result['success'],
        'error_code': result.get('errorCode', ''), 'error_message': result.get('errorMessage', ''),
        'confidence': float(quality.get('fitness', 0)), 'layer_no': int(layer_no),
        'pointcloud_token': token, 'raw_data_path': token,
        'plc_publish_allowed': False, 'compensation_valid': False,
        'robot_groups': {},
        'plc_payload': {'compensation_valid': False, 'plc_publish_allowed': False},
    }
    if result['points'] and result['points'][0].get('xyz') is not None:
        point = result['points'][0]['xyz']
        payload.update({f'actual_{axis}': float(point[i]) for i, axis in enumerate('xyz')})
    payload.update({f'offset_{axis}': float(offsets[0][i]) for i, axis in enumerate('xyz')})
    payload['offset_rz'] = 0.
    # Assemble calibrated robot-base reference-point differences for result output.
    if robot and robot.get('success'):
        for i, name in enumerate(('A', 'B')[:len(offsets)]):
            payload['robot_groups'][name] = {
                'coordinate_system': 'robot_base',
                'translation_mm': dict(zip('xyz', offsets[i])),
                'rotation_deg': {'rz': 0.}, 'plc_publish_allowed': False,
            }
    # Use the same concrete validation for history and automatic PLC output.
    # Keep legacy flags as derived metadata only, never as an input gate.
    from apps.devices.plc_position_debug import dual_group_position
    converted = dual_group_position(payload, recipe)
    allowed = converted['is_success']
    payload['locate_ok'] = payload['is_success'] = allowed
    if not allowed:
        payload['error_message'] = converted['error_message']
        if not payload['error_code']:
            payload['error_code'] = ('ROBOT_CALIBRATION' if not robot or not robot.get('success')
                                     else 'COMPENSATION_INVALID')
    payload['plc_publish_allowed'] = payload['compensation_valid'] = allowed
    payload['plc_payload'].update(plc_publish_allowed=allowed, compensation_valid=allowed)
    for group in payload['robot_groups'].values():
        group['plc_publish_allowed'] = allowed
    timings = {'registration_ms': round((matched - started) * 1000, 1),
               'projection_validation_ms': round((perf_counter() - matched) * 1000, 1)}
    payload['timings_ms'] = timings
    if save_record:
        saving = perf_counter()
        record = save_result(recipe, payload, layer_no=layer_no, token=token, product=product, rack=rack, task=task)
        save_history_images(record, cloud, token, camera_image=camera_image)
        payload['result_id'], payload['task_id'] = record.pk, record.vision_task_id
        timings['result_images_ms'] = round((perf_counter() - saving) * 1000, 1)
        archiving = perf_counter()
        original = record.vision_task.images.filter(image_type='ORIGINAL').last()
        archive_history(record.vision_task, recipe, layer_no, cloud, metadata, payload,
                        original.file.path if original else None)
        timings['archive_ms'] = round((perf_counter() - archiving) * 1000, 1)
        timings['total_ms'] = round((perf_counter() - started) * 1000, 1)
        RackLocationResult.objects.filter(pk=record.pk).update(result_data=payload)
        from apps.devices.listener_logs import record as log_event
        log_event('3d', f'任务 #{record.vision_task_id} 耗时：配准 {timings["registration_ms"]} ms，投影及校验 {timings["projection_validation_ms"]} ms，结果及图像保存 {timings["result_images_ms"]} ms，点云归档 {timings["archive_ms"]} ms')
    return payload


def archive_history(task, recipe, layer_no, cloud, metadata, result, image_path):
    from django.conf import settings
    from .offline_data_service import OfflineDataPackageService
    from .offline_data_views import _hand_eye_matrix, _robot_pose_matrix

    service = OfflineDataPackageService(base_dir=settings.VISION_HISTORY_PACKAGE_DIR)
    return service.create_package(
        cloud, _hand_eye_matrix(recipe), _robot_pose_matrix(recipe), recipe.roi_config,
        recipe, layer_no, {**metadata.get('camera', {}), 'source': metadata.get('source', 'unknown')},
        result=result, image_2d_path=image_path, history_task=task,
    )


def save_result(recipe, payload, *, layer_no, token='', product=None, rack=None, task=None):
    def decimal(value):
        return Decimal(str(float(value))).quantize(Decimal('0.001'))
    with transaction.atomic():
        task_values = dict(
            task_type=VisionTaskType.RACK_LOCATING, product=product, rack=rack,
            status=ResultStatus.SUCCESS if payload['locate_ok'] else ResultStatus.FAILED,
            started_at=timezone.now(), finished_at=timezone.now(),
            error_message=payload.get('error_message', ''),
        )
        if task is None:
            task = VisionTask.objects.create(**task_values)
        else:
            for name in ('status', 'finished_at', 'error_message'):
                setattr(task, name, task_values[name])
            task.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])
        return RackLocationResult.objects.create(
            vision_task=task, recipe=recipe, rack=rack, side=recipe.rack_side,
            position_no=recipe.position_no, layer_no=layer_no,
            **{f'actual_{axis}': decimal(payload[f'actual_{axis}']) for axis in 'xyz' if f'actual_{axis}' in payload},
            **{f'offset_{axis}': decimal(payload[f'offset_{axis}']) for axis in 'xyz'},
            confidence=decimal(payload['confidence']), is_success=payload['locate_ok'],
            is_recipe_matched=payload['locate_ok'], error_code=payload.get('error_code', ''),
            error_message=payload.get('error_message', ''), raw_data_path=token,
            roi_data=(recipe.roi_config or {}).get('cloud_center_config') or {},
            result_data=payload, plc_write_status='SKIPPED',
        )


def save_history_images(record, cloud, token, camera_image=None):
    """Store independent depth, camera and annotated result snapshots per record."""
    from pathlib import Path
    import cv2
    import numpy as np
    from django.conf import settings
    from django.core.files.base import ContentFile
    from .algorithms.image_io import pointcloud_to_preview
    from .models import VisionImage

    # Capture already persisted these immutable images. Reuse them instead of
    # regenerating the depth preview and re-encoding the original PNG.
    existing = {item.image_type: item for item in record.vision_task.images.all()
                if item.file and item.file.storage.exists(item.file.name)}
    images = []
    if 'DEPTH' not in existing:
        images.append(('DEPTH', np.asarray(pointcloud_to_preview(cloud), dtype=np.uint8)))
    media = Path(settings.MEDIA_ROOT).resolve()
    raw = (media / token).resolve() if token else None
    camera = camera_image
    if camera is None and raw and raw.is_relative_to(media):
        sibling = raw.with_name(raw.stem + '_image2d.png')
        if sibling.is_file():
            camera = cv2.imdecode(np.fromfile(sibling, np.uint8), cv2.IMREAD_COLOR)
    if camera is not None and 'ORIGINAL' not in existing:
        images.append(('ORIGINAL', camera))
    if camera is not None:
        annotated = annotate_camera_rois(camera, record.roi_data or {})
        cv2.putText(annotated, 'OK' if record.is_success else 'NG', (12, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 180, 0) if record.is_success else (0, 0, 255), 2)
        images.append(('RESULT', annotated))
    for kind, image in images:
        ok, encoded = cv2.imencode('.png', image)
        if not ok:
            raise OSError('3D 历史图像保存失败')
        item = VisionImage(vision_task_id=record.vision_task_id, image_type=kind,
                           width=image.shape[1], height=image.shape[0], captured_at=timezone.now())
        name = f'vision/history/{record.vision_task_id}/{kind.lower()}.png'
        item.file.name = item.file.storage.save(name, ContentFile(encoded.tobytes()))
        item.save()
        if kind == 'RESULT':
            record.result_image_path = item.file.name
            record.save(update_fields=['result_image_path'])


def annotate_camera_rois(image, config):
    """Draw the capture-time recipe's pixel ROIs on its 2D camera frame."""
    import cv2
    import math
    annotated = image.copy()
    height, width = annotated.shape[:2]
    size = config.get('imageSize') or [width, height]
    sx, sy = width / float(size[0]), height / float(size[1])
    for index, roi in enumerate(config.get('rois') or []):
        x, y = float(roi['x']), float(roi['y'])
        w, h = float(roi.get('width', roi.get('w'))), float(roi.get('height', roi.get('h')))
        if not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
            continue
        p0 = (round(x * sx), round(y * sy))
        p1 = (round((x + w) * sx), round((y + h) * sy))
        cv2.rectangle(annotated, p0, p1, (255, 200, 0), 2)
        cv2.putText(annotated, str(roi.get('target') or f'ROI {index+1}'),
                    (p0[0], max(14, p0[1]-5)), cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 200, 0), 1)
    return annotated
