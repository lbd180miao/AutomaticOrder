"""Two camera point displacements in robot base coordinates. No PLC I/O."""
import numpy as np

from .coordinate_transform import CoordinateTransformService
from .models_hand_eye import HandEyeCalibration


def workspace_context():
    from .views_hand_eye import _validate_homogeneous_matrix
    calibration = HandEyeCalibration.objects.filter(is_active=True).first()
    if calibration is None:
        raise ValueError('请在手眼标定页面激活标定配置')
    pose = (calibration.calibration_params or {}).get('T_base_flange')
    if not pose:
        raise ValueError('请在手眼标定页面保存拍照机器人姿态')
    matrices = {}
    for key, value in [('T_flange_camera', calibration.T_flange_camera), ('T_base_flange', pose)]:
        matrix = CoordinateTransformService.parse_matrix_from_json(value)
        _validate_homogeneous_matrix(matrix, key)
        matrices[key] = matrix.tolist()
    return {**matrices, 'calibration_id': calibration.pk, 'calibration_name': calibration.name,
            'pose_source': 'hand_eye_workspace_saved_pose'}


def robot_point_difference(current, reference, context):
    from .views_hand_eye import _validate_homogeneous_matrix
    def transform(ctx):
        matrices = []
        for key in ('T_base_flange', 'T_flange_camera'):
            matrix = np.asarray(ctx[key], float)
            _validate_homogeneous_matrix(matrix, key)
            matrices.append(matrix)
        return matrices[0] @ matrices[1]

    def points(measurement):
        if not measurement or not measurement.get('success') or measurement.get('coordinateSystem') != 'camera' or measurement.get('unit') != 'mm':
            raise ValueError('需要有效的相机坐标模板和当前测量结果')
        by_name = {p['name']: p for p in measurement['points']}
        result = np.asarray([by_name[name]['xyz'] for name in ('P1', 'P2')], float)
        if result.shape != (2, 3) or not np.isfinite(result).all() or not all(by_name[n].get('success') for n in ('P1', 'P2')):
            raise ValueError('缺少有效的 P1、P2 坐标')
        return result

    standard = (reference or {}).get('measurement')
    previous = (standard or {}).get('robot_transform_context')
    # Existing camera templates have no robot pose: show the explicit same-pose assumption.
    reference_context = previous or context
    if previous and not np.allclose(previous['T_flange_camera'], context['T_flange_camera'], atol=1e-8):
        raise ValueError('手眼矩阵与模板保存时不同，请重新示教标准模板')
    tc, ts = transform(context), transform(reference_context)
    cur = points(current) @ tc[:3, :3].T + tc[:3, 3]
    std = points(standard) @ ts[:3, :3].T + ts[:3, 3]
    return {'success': True, 'coordinateSystem': 'robot_base', 'unit': 'mm',
            'standard': std.tolist(), 'current': cur.tolist(), 'offsets': (cur-std).tolist(),
            'context': context, 'reference_context': reference_context,
            'same_pose_assumed': previous is None, 'plc_publish_allowed': False}


def evaluate_robot_points(current, reference):
    try:
        context = workspace_context()
        if current.get('success'):
            current['robot_transform_context'] = context
        return robot_point_difference(current, reference, context)
    except (ValueError, KeyError, TypeError) as exc:
        return {'success': False, 'errorMessage': str(exc), 'plc_publish_allowed': False}
