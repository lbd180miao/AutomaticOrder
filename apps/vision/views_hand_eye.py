"""
手眼标定视图
"""
import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator

from .models_hand_eye import HandEyeCalibration, HandEyeCalibrationSample, HandEyeVerificationResult
from .hand_eye_service import HandEyeCalibrationService
from .coordinate_transform import CoordinateTransformService
from apps.devices.models import Device
from apps.devices.services import DeviceService

logger = logging.getLogger(__name__)

# 初始化服务
hand_eye_service = HandEyeCalibrationService()
transform_service = CoordinateTransformService()
device_service = DeviceService()


def api_response(data=None, error=None, status=200):
    """统一API响应格式"""
    if error:
        return JsonResponse({
            'success': False,
            'error': error
        }, status=status)
    
    return JsonResponse({
        'success': True,
        'data': data
    }, status=status)


# ========== 页面视图 ==========

@require_http_methods(["GET"])
def hand_eye_page(request):
    """手眼标定管理页面（简化版 - 只需输入矩阵）"""
    from apps.core.constants import DeviceType
    
    # 获取当前激活的手眼标定
    active_calibration = HandEyeCalibration.objects.filter(is_active=True).first()

    # 获取所有机器人和相机设备供选择
    robots = Device.objects.filter(device_type__in=[
        DeviceType.INJECTION_ROBOT,
        DeviceType.BOXING_ROBOT
    ])
    cameras = Device.objects.filter(device_type=DeviceType.DEPTH_CAMERA)
    
    # 获取历史记录
    history_list = HandEyeCalibration.objects.all().order_by('-created_at')[:20]
    active_capture_pose_matrix = None
    if active_calibration:
        active_capture_pose_matrix = (
            (active_calibration.calibration_params or {}).get('T_base_flange')
        )
    
    return render(request, 'vision/hand_eye_calibration.html', {
        'active_calibration': active_calibration,
        'robots': robots,
        'cameras': cameras,
        'history_list': history_list,
        'active_capture_pose_matrix': active_capture_pose_matrix,
    })


# ========== 标定CRUD ==========

@require_http_methods(["GET"])
def list_calibrations(request):
    """获取标定列表"""
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        robot_id = request.GET.get('robot_id')
        camera_id = request.GET.get('camera_id')
        is_active = request.GET.get('is_active')
        
        queryset = HandEyeCalibration.objects.all()
        
        if robot_id:
            queryset = queryset.filter(robot_device_id=robot_id)
        if camera_id:
            queryset = queryset.filter(camera_device_id=camera_id)
        if is_active is not None:
            queryset = queryset.filter(is_active=(is_active.lower() == 'true'))
        
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        
        calibrations = [{
            'id': cal.id,
            'name': cal.name,
            'robot_device': {
                'id': cal.robot_device.id,
                'code': cal.robot_device.code,
                'name': cal.robot_device.name
            },
            'camera_device': {
                'id': cal.camera_device.id,
                'code': cal.camera_device.code,
                'name': cal.camera_device.name
            },
            'calibration_method': cal.calibration_method,
            'calibration_error': float(cal.calibration_error),
            'sample_count': cal.sample_count,
            'is_active': cal.is_active,
            'verified_at': cal.verified_at.isoformat() if cal.verified_at else None,
            'created_at': cal.created_at.isoformat(),
            'description': cal.description,
            'operator': cal.operator,
        } for cal in page_obj]
        
        return api_response(data={
            'calibrations': calibrations,
            'total': paginator.count,
            'page': page,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
        })
    
    except Exception as e:
        logger.exception("获取标定列表失败")
        return api_response(error=str(e), status=500)


@require_http_methods(["GET"])
def get_calibration(request, calibration_id):
    """获取标定详情"""
    try:
        calibration = get_object_or_404(HandEyeCalibration, id=calibration_id)
        
        result = {
            'id': calibration.id,
            'name': calibration.name,
            'robot_device': {
                'id': calibration.robot_device.id,
                'code': calibration.robot_device.code,
                'name': calibration.robot_device.name
            },
            'camera_device': {
                'id': calibration.camera_device.id,
                'code': calibration.camera_device.code,
                'name': calibration.camera_device.name
            },
            'T_flange_camera': calibration.T_flange_camera,
            'calibration_method': calibration.calibration_method,
            'calibration_error': float(calibration.calibration_error),
            'sample_count': calibration.sample_count,
            'calibration_params': calibration.calibration_params,
            'is_active': calibration.is_active,
            'verified_at': calibration.verified_at.isoformat() if calibration.verified_at else None,
            'created_at': calibration.created_at.isoformat(),
            'updated_at': calibration.updated_at.isoformat(),
            'description': calibration.description,
            'operator': calibration.operator,
        }
        
        return api_response(data=result)
    
    except Exception as e:
        logger.exception("获取标定详情失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def create_calibration(request):
    """创建标定"""
    try:
        data = json.loads(request.body)
        
        calibration = hand_eye_service.create_calibration(
            name=data['name'],
            robot_device_id=data['robot_device_id'],
            camera_device_id=data['camera_device_id'],
            description=data.get('description', ''),
            operator=data.get('operator', '')
        )
        
        return api_response(data={
            'id': calibration.id,
            'name': calibration.name,
            'message': '标定任务创建成功'
        })
    
    except Exception as e:
        logger.exception("创建标定失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
def update_calibration(request, calibration_id):
    """更新标定"""
    try:
        calibration = get_object_or_404(HandEyeCalibration, id=calibration_id)
        data = json.loads(request.body)
        
        # 更新可修改字段
        if 'name' in data:
            calibration.name = data['name']
        if 'description' in data:
            calibration.description = data['description']
        if 'operator' in data:
            calibration.operator = data['operator']
        if 'T_flange_camera' in data:
            matrix = transform_service.parse_matrix_from_json(data['T_flange_camera'])
            _validate_homogeneous_matrix(matrix, 'T_flange_camera')
            calibration.T_flange_camera = {'matrix': matrix.tolist()}
        if 'T_base_flange' in data:
            matrix = transform_service.parse_matrix_from_json(data['T_base_flange'])
            _validate_homogeneous_matrix(matrix, 'T_base_flange')
            calibration_params = dict(calibration.calibration_params or {})
            calibration_params['T_base_flange'] = {'matrix': matrix.tolist()}
            calibration.calibration_params = calibration_params
        
        calibration.save()
        
        return api_response(data={
            'message': '矩阵保存成功',
            'T_flange_camera': calibration.T_flange_camera,
            'T_base_flange': (calibration.calibration_params or {}).get('T_base_flange'),
        })
    
    except (json.JSONDecodeError, ValueError) as e:
        return api_response(error=str(e), status=400)
    except Exception as e:
        logger.exception("更新标定失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_calibration(request, calibration_id):
    """删除标定"""
    try:
        calibration = get_object_or_404(HandEyeCalibration, id=calibration_id)
        name = calibration.name
        calibration.delete()
        
        return api_response(data={'message': f'标定 {name} 已删除'})
    
    except Exception as e:
        logger.exception("删除标定失败")
        return api_response(error=str(e), status=500)


# ========== 样本管理 ==========

@require_http_methods(["GET"])
def list_samples(request, calibration_id):
    """获取标定样本列表"""
    try:
        calibration = get_object_or_404(HandEyeCalibration, id=calibration_id)
        samples = calibration.samples.all()
        
        result = [{
            'id': sample.id,
            'sample_index': sample.sample_index,
            'T_base_flange': sample.T_base_flange,
            'T_camera_target': sample.T_camera_target,
            'detection_success': sample.detection_success,
            'reprojection_error': float(sample.reprojection_error),
            'capture_record_id': sample.capture_record_id,
            'notes': sample.notes,
            'created_at': sample.created_at.isoformat(),
        } for sample in samples]
        
        return api_response(data={
            'samples': result,
            'total': len(result)
        })
    
    except Exception as e:
        logger.exception("获取样本列表失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def add_sample(request, calibration_id):
    """添加标定样本"""
    try:
        data = json.loads(request.body)
        
        sample = hand_eye_service.add_sample(
            calibration_id=calibration_id,
            T_base_flange=data['T_base_flange'],
            T_camera_target=data['T_camera_target'],
            capture_record_id=data.get('capture_record_id'),
            detection_success=data.get('detection_success', True),
            reprojection_error=data.get('reprojection_error', 0.0),
            notes=data.get('notes', '')
        )
        
        return api_response(data={
            'id': sample.id,
            'sample_index': sample.sample_index,
            'message': f'样本 #{sample.sample_index} 已添加'
        })
    
    except Exception as e:
        logger.exception("添加样本失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_sample(request, sample_id):
    """删除标定样本"""
    try:
        success = hand_eye_service.delete_sample(sample_id)
        
        if success:
            return api_response(data={'message': '样本已删除'})
        else:
            return api_response(error='样本不存在', status=404)
    
    except Exception as e:
        logger.exception("删除样本失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def clear_samples(request, calibration_id):
    """清空所有样本"""
    try:
        count = hand_eye_service.clear_samples(calibration_id)
        
        return api_response(data={
            'message': f'已清空 {count} 个样本'
        })
    
    except Exception as e:
        logger.exception("清空样本失败")
        return api_response(error=str(e), status=500)


# ========== 标定计算和激活 ==========

@csrf_exempt
@require_http_methods(["POST"])
def compute_calibration(request, calibration_id):
    """计算标定"""
    try:
        data = json.loads(request.body) if request.body else {}
        method = data.get('method', 'OPENCV_TSAI')
        
        result = hand_eye_service.compute_calibration(
            calibration_id=calibration_id,
            method=method
        )
        
        return api_response(data=result)
    
    except ValueError as e:
        return api_response(error=str(e), status=400)
    except Exception as e:
        logger.exception("计算标定失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def activate_calibration(request, calibration_id):
    """激活标定"""
    try:
        calibration = hand_eye_service.activate_calibration(calibration_id)
        
        return api_response(data={
            'id': calibration.id,
            'name': calibration.name,
            'is_active': calibration.is_active,
            'message': f'标定 {calibration.name} 已激活'
        })
    
    except Exception as e:
        logger.exception("激活标定失败")
        return api_response(error=str(e), status=500)


# ========== 标定验证 ==========

@csrf_exempt
@require_http_methods(["POST"])
def verify_calibration(request, calibration_id):
    """验证标定"""
    try:
        data = json.loads(request.body)
        
        verification = hand_eye_service.verify_calibration(
            calibration_id=calibration_id,
            T_base_flange=data['T_base_flange'],
            test_points_camera=data['test_points_camera'],
            ground_truth_points=data.get('ground_truth_points'),
            error_threshold=data.get('error_threshold', 5.0),
            notes=data.get('notes', '')
        )
        
        return api_response(data={
            'id': verification.id,
            'mean_error': float(verification.mean_error),
            'max_error': float(verification.max_error),
            'std_error': float(verification.std_error),
            'is_passed': verification.is_passed,
            'test_points_robot': verification.test_points_robot,
            'message': f'验证{"通过" if verification.is_passed else "失败"}，平均误差={verification.mean_error:.2f}mm'
        })
    
    except Exception as e:
        logger.exception("验证标定失败")
        return api_response(error=str(e), status=500)


@require_http_methods(["GET"])
def list_verifications(request, calibration_id):
    """获取验证记录列表"""
    try:
        calibration = get_object_or_404(HandEyeCalibration, id=calibration_id)
        verifications = calibration.verification_results.all()
        
        result = [{
            'id': ver.id,
            'mean_error': float(ver.mean_error),
            'max_error': float(ver.max_error),
            'std_error': float(ver.std_error),
            'is_passed': ver.is_passed,
            'error_threshold': float(ver.error_threshold),
            'created_at': ver.created_at.isoformat(),
            'notes': ver.notes,
        } for ver in verifications]
        
        return api_response(data={
            'verifications': result,
            'total': len(result)
        })
    
    except Exception as e:
        logger.exception("获取验证记录失败")
        return api_response(error=str(e), status=500)


# ========== 导入导出 ==========

@require_http_methods(["GET"])
def export_calibration(request, calibration_id):
    """导出标定"""
    try:
        export_data = hand_eye_service.export_calibration(calibration_id)
        
        return api_response(data=export_data)
    
    except Exception as e:
        logger.exception("导出标定失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def import_calibration(request):
    """导入标定"""
    try:
        data = json.loads(request.body)
        
        calibration = hand_eye_service.import_calibration(
            import_data=data['calibration_data'],
            robot_device_id=data['robot_device_id'],
            camera_device_id=data['camera_device_id']
        )
        
        return api_response(data={
            'id': calibration.id,
            'name': calibration.name,
            'message': '标定导入成功'
        })
    
    except Exception as e:
        logger.exception("导入标定失败")
        return api_response(error=str(e), status=500)


# ========== 辅助接口 ==========

@csrf_exempt
@require_http_methods(["POST", "GET"])
def get_robot_pose(request):
    """获取机器人当前位姿"""
    try:
        if request.method == "POST":
            data = json.loads(request.body)
            robot_code = data.get('robot_code', 'ROBOT-01')
        else:
            robot_code = request.GET.get('robot_code', 'ROBOT-01')
        
        # 从PLC读取机器人位姿
        pose_data = device_service.adapter.read_robot_pose(robot_code)
        
        return api_response(data=pose_data)
    
    except Exception as e:
        logger.exception("获取机器人位姿失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def test_transform(request):
    """测试坐标转换"""
    try:
        data = json.loads(request.body)
        
        # 解析输入
        P_camera = data['P_camera']  # [[x, y, z], ...] 或 [x, y, z]
        T_flange_camera = transform_service.parse_matrix_from_json(data['T_flange_camera'])
        T_base_flange = transform_service.parse_matrix_from_json(data['T_base_flange'])
        
        # 执行转换
        result = transform_service.verify_transform_chain(
            P_camera=P_camera,
            T_flange_camera=T_flange_camera,
            T_base_flange=T_base_flange,
            P_expected_base=data.get('P_expected_base'),
            tolerance=data.get('tolerance', 5.0)
        )
        
        return api_response(data=result)
    
    except Exception as e:
        logger.exception("测试坐标转换失败")
        return api_response(error=str(e), status=500)


# ========== 坐标系偏差转换 ==========

@csrf_exempt
@require_http_methods(["POST"])
def compute_delta(request):
    """
    核心计算接口：相机坐标系偏差 → 机器人基坐标系偏差

    算法：
        T_base_cam = T_base_flange × T_flange_camera
        ΔT_base    = T_base_cam × ΔT_cam × inv(T_base_cam)

    请求体（JSON）：
        delta_T_cam      : {matrix: [[...]]}（优先）相机坐标系原始偏差矩阵
        delta_cam        : {x, y, z, rx, ry, rz}（兼容）相机坐标系偏差（mm / 度）
        T_base_flange    : {x, y, z, rx, ry, rz} 或 {matrix: [[...]]} 拍照时机器人位姿
        calibration_id   : int（可选，不传则使用当前激活标定）
        T_flange_camera  : 4×4矩阵（可选；手动调试时优先于 calibration_id）

    返回：
        delta_base       : {x, y, z, rx, ry, rz}  机器人基坐标系偏差
        T_flange_camera  : 4×4矩阵
        T_base_cam       : 4×4矩阵（中间矩阵，供调试）
        delta_T_base     : 4×4矩阵（完整结果）
        calibration_name : 使用的标定名称
    """
    try:
        try:
            data = json.loads(request.body.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return api_response(error=f'请求体不是有效 JSON：{exc}', status=400)

        if not isinstance(data, dict):
            return api_response(error='请求体必须是 JSON 对象', status=400)

        # ── 1. 解析 ΔT_cam（相机坐标系偏差）──
        # 记录页优先传入原始 4×4 矩阵，避免先分解再重建造成精度损失；
        # 保留 delta_cam 六自由度输入以兼容旧调用方。
        delta_T_cam_raw = data.get('delta_T_cam')
        if delta_T_cam_raw is not None:
            delta_T_cam = transform_service.parse_matrix_from_json(delta_T_cam_raw)
            _validate_homogeneous_matrix(delta_T_cam, 'delta_T_cam')
            delta_cam_pose = transform_service.matrix_to_pose(delta_T_cam)
        else:
            dc = data.get('delta_cam')
            delta_cam_pose = _parse_six_dof(dc, 'delta_cam')
            delta_T_cam = transform_service.parse_matrix_from_json(delta_cam_pose)

        # ── 2. 解析 T_base_flange（拍照时机器人位姿）──
        T_base_flange_raw = data.get('T_base_flange')
        if T_base_flange_raw is None:
            return api_response(error='缺少 T_base_flange（拍照时机器人位姿）', status=400)
        if isinstance(T_base_flange_raw, dict) and 'matrix' not in T_base_flange_raw:
            T_base_flange_raw = _parse_six_dof(T_base_flange_raw, 'T_base_flange')
        T_base_flange = transform_service.parse_matrix_from_json(T_base_flange_raw)
        _validate_homogeneous_matrix(T_base_flange, 'T_base_flange')

        # ── 3. 获取手眼矩阵 T_flange_camera ──
        manual_hand_eye = data.get('T_flange_camera')
        calibration_id = data.get('calibration_id')
        if manual_hand_eye is not None:
            T_flange_camera = transform_service.parse_matrix_from_json(manual_hand_eye)
            calibration = None
        else:
            if calibration_id is not None:
                if isinstance(calibration_id, bool):
                    raise ValueError('calibration_id 必须是正整数')
                try:
                    calibration_id = int(calibration_id)
                except (TypeError, ValueError):
                    raise ValueError('calibration_id 必须是正整数')
                if calibration_id <= 0:
                    raise ValueError('calibration_id 必须是正整数')
                calibration = HandEyeCalibration.objects.filter(id=calibration_id).first()
                if calibration is None:
                    return api_response(error=f'未找到 ID 为 {calibration_id} 的手眼标定', status=404)
            else:
                calibration = HandEyeCalibration.objects.filter(is_active=True).first()
            if calibration is None:
                return api_response(error='未找到激活的手眼标定，请先激活一个标定配置', status=400)
            T_flange_camera = transform_service.parse_matrix_from_json(calibration.T_flange_camera)

        _validate_homogeneous_matrix(T_flange_camera, 'T_flange_camera')

        # ── 4. 核心计算 ──
        # T_base_cam：相机坐标系 → 机器人基坐标系的完整变换
        T_base_cam = T_base_flange @ T_flange_camera
        T_base_cam_inv = transform_service.invert_transform(T_base_cam)

        # 相似变换：将相机坐标系里的偏差矩阵转换到机器人基坐标系
        delta_T_base = T_base_cam @ delta_T_cam @ T_base_cam_inv

        # ── 5. 提取 6DOF 偏差值 ──
        delta_base_pose = transform_service.matrix_to_pose(delta_T_base)

        logger.info(
            "compute_delta 完成 | 标定=%s | "
            "ΔCam=(%.2f,%.2f,%.2f,%.2f°,%.2f°,%.2f°) | "
            "ΔBase=(%.2f,%.2f,%.2f,%.2f°,%.2f°,%.2f°)",
            calibration.name if calibration else '手动输入',
            delta_cam_pose['x'], delta_cam_pose['y'], delta_cam_pose['z'],
            delta_cam_pose['rx'], delta_cam_pose['ry'], delta_cam_pose['rz'],
            delta_base_pose['x'], delta_base_pose['y'], delta_base_pose['z'],
            delta_base_pose['rx'], delta_base_pose['ry'], delta_base_pose['rz'],
        )

        return api_response(data={
            'delta_base':       delta_base_pose,
            'delta_T_base':     delta_T_base.tolist(),
            'T_flange_camera':  T_flange_camera.tolist(),
            'T_base_flange':    T_base_flange.tolist(),
            'T_base_cam':       T_base_cam.tolist(),
            'delta_T_cam':      delta_T_cam.tolist(),
            'calibration_id':   calibration.id if calibration else None,
            'calibration_name': calibration.name if calibration else '手动输入',
        })

    except ValueError as e:
        return api_response(error=str(e), status=400)
    except Exception as e:
        logger.exception("compute_delta 计算失败")
        return api_response(error=str(e), status=500)


def _parse_six_dof(value, field_name):
    """严格解析接口中的六自由度对象，避免缺字段被静默补零。"""
    if not isinstance(value, dict):
        raise ValueError(f'{field_name} 必须是包含 x、y、z、rx、ry、rz 的对象')

    fields = ('x', 'y', 'z', 'rx', 'ry', 'rz')
    missing = [field for field in fields if field not in value]
    if missing:
        raise ValueError(f'{field_name} 缺少字段：{", ".join(missing)}')

    parsed = {}
    for field in fields:
        raw_value = value[field]
        if isinstance(raw_value, bool):
            raise ValueError(f'{field_name}.{field} 必须是有限数值')
        try:
            parsed[field] = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f'{field_name}.{field} 必须是有限数值')

    import numpy as np
    if not np.isfinite(list(parsed.values())).all():
        raise ValueError(f'{field_name} 的所有字段都必须是有限数值')
    return parsed


def _validate_homogeneous_matrix(matrix, field_name):
    """验证有限值、齐次末行以及旋转部分，确保刚体逆变换成立。"""
    import numpy as np

    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError(f'{field_name} 必须是有限数值组成的 4×4 矩阵')
    if not np.allclose(matrix[3], [0.0, 0.0, 0.0, 1.0], atol=1e-8):
        raise ValueError(f'{field_name} 的最后一行必须为 [0, 0, 0, 1]')
    valid, message = transform_service.validate_rotation_matrix(matrix[:3, :3])
    if not valid:
        raise ValueError(f'{field_name} 无效：{message}')


# ========== 坐标 ROI 转换（从 coordinates app 迁移）==========

@csrf_exempt
@require_http_methods(["POST"])
def api_coord_transform_roi(request):
    """
    将相机坐标系 ROI 转换为机器人基坐标系 AABB。

    从 coordinates app 迁移至此，供配方页面（rack_location_recipe_form、
    rack_location_recipes）调用，避免依赖已注释的 coordinates URL。

    请求体（JSON）：
      layer_no   : 层号 1/2/3
      camera_roi : {x_min, x_max, y_min, y_max, z_min, z_max}
      recipe_id  : 可选，配方 ID
    """
    from apps.coordinates.services import CoordinateWorkbenchService, CoordinateWorkbenchError

    try:
        body = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return api_response(error=f'请求体不是有效 JSON：{exc}', status=400)

    if not isinstance(body, dict):
        return api_response(error='请求体必须是 JSON 对象', status=400)

    try:
        data = CoordinateWorkbenchService().transform_camera_roi(
            layer_no=body.get('layer_no'),
            camera_roi=body.get('camera_roi'),
            recipe_id=body.get('recipe_id'),
        )
        return api_response(data=data)

    except CoordinateWorkbenchError as exc:
        return JsonResponse({
            'success': False,
            'data': None,
            'error': {'code': exc.code, 'message': exc.message, 'fields': exc.fields},
        }, status=exc.status)
    except Exception as exc:
        logger.exception('坐标 ROI 转换失败', exc_info=exc)
        return api_response(error='坐标 ROI 转换内部错误', status=500)
