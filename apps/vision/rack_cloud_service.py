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
                   product=None, rack=None, algorithm='cloud_match'):
    config_key, reference_key = algorithm_keys(algorithm)
    reference = (recipe.roi_config or {}).get(reference_key)
    config = (recipe.roi_config or {}).get(config_key) or {}
    if reference and required_targets(config) != required_targets(reference['config']):
        raise ValueError('料架层数与标准模板不同，请重新保存点云标准模板')
    if algorithm == 'cloud_center' and reference and config != reference['config']:
        raise ValueError('ROI 已变化，请重新保存当前算法的点云标准模板')
    result = match_template(cloud, metadata, reference)
    result = add_display_pixels(result, cloud, metadata)
    robot = evaluate_robot_points(result, reference) if result['success'] else None
    offsets = robot['offsets'] if robot and robot.get('success') else [[0, 0, 0], [0, 0, 0]]
    quality = result.get('registration') or {}
    payload = {
        'algorithm_version': VERSION, 'source': 'cloud_match', 'result': result,
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
    # Display both calibrated reference-point differences; do not grant PLC approval.
    if robot and robot.get('success'):
        for i, name in enumerate(('A', 'B')[:len(offsets)]):
            payload['robot_groups'][name] = {
                'coordinate_system': 'robot_base',
                'translation_mm': dict(zip('xyz', offsets[i])),
                'rotation_deg': {'rz': 0.}, 'plc_publish_allowed': False,
            }
    if save_record:
        record = save_result(recipe, payload, layer_no=layer_no, token=token, product=product, rack=rack)
        payload['result_id'], payload['task_id'] = record.pk, record.vision_task_id
    return payload


def save_result(recipe, payload, *, layer_no, token='', product=None, rack=None):
    def decimal(value):
        return Decimal(str(float(value))).quantize(Decimal('0.001'))
    with transaction.atomic():
        task = VisionTask.objects.create(
            task_type=VisionTaskType.RACK_LOCATING, product=product, rack=rack,
            status=ResultStatus.SUCCESS if payload['locate_ok'] else ResultStatus.FAILED,
            started_at=timezone.now(), finished_at=timezone.now(),
            error_message=payload.get('error_message', ''),
        )
        return RackLocationResult.objects.create(
            vision_task=task, recipe=recipe, rack=rack, side=recipe.rack_side,
            position_no=recipe.position_no, layer_no=layer_no,
            **{f'actual_{axis}': decimal(payload[f'actual_{axis}']) for axis in 'xyz'},
            **{f'offset_{axis}': decimal(payload[f'offset_{axis}']) for axis in 'xyz'},
            confidence=decimal(payload['confidence']), is_success=payload['locate_ok'],
            is_recipe_matched=payload['locate_ok'], error_code=payload.get('error_code', ''),
            error_message=payload.get('error_message', ''), raw_data_path=token,
            roi_data=(recipe.roi_config or {}).get('cloud_match_config') or {},
            result_data=payload, plc_write_status='SKIPPED',
        )
