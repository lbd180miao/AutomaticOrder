"""Shared point-cloud registration for workbench, offline and production entry points."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.constants import ResultStatus, VisionTaskType
from .models import RackLocationResult, VisionTask
from .rack_cloud_match import VERSION, match_template, add_display_pixels
from .rack_cloud_roi import required_targets, algorithm_keys
from .rack_robot_points import evaluate_robot_points


def evaluate_cloud(recipe, cloud, metadata, *, layer_no=1, token='', save_record=False,
                   product=None, rack=None, algorithm='cloud_center', camera_image=None, task=None):
    config_key, reference_key = algorithm_keys(algorithm)
    reference = (recipe.roi_config or {}).get(reference_key)
    config = (recipe.roi_config or {}).get(config_key) or {}
    if reference and required_targets(config) != required_targets(reference['config']):
        raise ValueError('料架层数与标准模板不同，请重新保存点云标准模板')
    if reference and config != reference['config']:
        raise ValueError('ROI 已变化，请重新保存当前算法的点云标准模板')
    result = match_template(cloud, metadata, reference)
    result = add_display_pixels(result, cloud, metadata)
    robot = evaluate_robot_points(result, reference) if result['success'] else None
    offsets = robot['offsets'] if robot and robot.get('success') else [[0, 0, 0], [0, 0, 0]]
    quality = result.get('registration') or {}
    payload = {
        'algorithm': 'cloud_center', 'algorithm_version': VERSION, 'source': 'cloud_match', 'result': result,
        'reference': {'measurement': reference['measurement']}, 'robot_result': robot,
        'locate_ok': result['success'], 'is_success': result['success'],
        'error_code': result.get('errorCode', ''), 'error_message': result.get('errorMessage', ''),
        'confidence': float(quality.get('fitness', 0)), 'layer_no': int(layer_no),
        'pointcloud_token': token, 'raw_data_path': token,
        'plc_publish_allowed': False, 'compensation_valid': False,
        'robot_groups': {},
        'plc_payload': {'compensation_valid': False, 'plc_publish_allowed': False},
    }
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
    if save_record:
        record = save_result(recipe, payload, layer_no=layer_no, token=token, product=product, rack=rack, task=task)
        save_history_images(record, cloud, token, camera_image=camera_image)
        payload['result_id'], payload['task_id'] = record.pk, record.vision_task_id
    return payload


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
            **{f'actual_{axis}': decimal(payload[f'actual_{axis}']) for axis in 'xyz'},
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

    depth = np.asarray(pointcloud_to_preview(cloud), dtype=np.uint8)
    images = [('DEPTH', depth)]
    media = Path(settings.MEDIA_ROOT).resolve()
    raw = (media / token).resolve() if token else None
    camera = camera_image
    if camera is None and raw and raw.is_relative_to(media):
        sibling = raw.with_name(raw.stem + '_image2d.png')
        if sibling.is_file():
            camera = cv2.imdecode(np.fromfile(sibling, np.uint8), cv2.IMREAD_COLOR)
    if camera is not None:
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
