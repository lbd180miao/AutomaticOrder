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
    """手眼标定管理页面"""
    # 获取所有机器人和相机设备
    from apps.core.constants import DeviceType
    
    robots = Device.objects.filter(device_type__in=[
        DeviceType.INJECTION_ROBOT,
        DeviceType.BOXING_ROBOT
    ])
    cameras = Device.objects.filter(device_type=DeviceType.DEPTH_CAMERA)
    
    calibrations = HandEyeCalibration.objects.all()[:10]
    
    return render(request, 'vision/hand_eye_calibration.html', {
        'robots': robots,
        'cameras': cameras,
        'calibrations': calibrations,
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
        
        calibration.save()
        
        return api_response(data={'message': '标定更新成功'})
    
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
