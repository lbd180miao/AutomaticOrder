"""
PLC补偿值写入模块 API视图
"""
import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .plc_writer_service import PLCCompensationWriter
from .compensation_calculator import CompensationData

logger = logging.getLogger(__name__)

# 初始化PLC写入器
plc_writer = PLCCompensationWriter()


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


# ========== PLC写入接口 ==========

@csrf_exempt
@require_http_methods(["POST"])
def write_compensation_to_plc(request):
    """
    写入补偿值到PLC
    
    请求体:
    {
        "compensation_x": -2.23,
        "compensation_y": 4.60,
        "compensation_z": 2.05,
        "compensation_rz": 0.0,
        "confidence_x": 1.0,
        "confidence_y": 1.0,
        "confidence_z": 0.624,
        "is_valid": true,
        "layer_no": 2,
        "position_no": 1,
        "rack_side": "BOTH",
        "recipe_id": 1,
        "validate": true
    }
    """
    try:
        data = json.loads(request.body)
        
        # 构建CompensationData对象
        compensation = CompensationData(
            compensation_x=data['compensation_x'],
            compensation_y=data['compensation_y'],
            compensation_z=data['compensation_z'],
            compensation_rz=data.get('compensation_rz', 0.0),
            confidence_x=data.get('confidence_x', 1.0),
            confidence_y=data.get('confidence_y', 1.0),
            confidence_z=data.get('confidence_z', 1.0),
            is_valid=data.get('is_valid', True),
            validation_message=data.get('validation_message', '')
        )
        
        # 写入PLC
        result = plc_writer.write_compensation_to_plc(
            compensation=compensation,
            layer_no=data['layer_no'],
            position_no=data.get('position_no'),
            rack_side=data.get('rack_side', 'BOTH'),
            recipe_id=data.get('recipe_id'),
            validate=data.get('validate', True)
        )
        
        if result.get('success'):
            return api_response(data=result)
        else:
            return api_response(
                error=result.get('error', '写入失败'),
                status=400
            )
    
    except KeyError as e:
        return api_response(error=f'缺少必需参数: {str(e)}', status=400)
    except Exception as e:
        logger.exception("写入补偿值到PLC失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def write_from_result(request):
    """
    从定位结果写入补偿值到PLC
    
    请求体:
    {
        "result_id": 123,
        "validate": true,
        "revalidate": true
    }
    """
    try:
        data = json.loads(request.body)
        
        result = plc_writer.write_compensation_from_result(
            result_id=data['result_id'],
            validate=data.get('validate', True),
            revalidate=data.get('revalidate', True)
        )
        
        if result.get('success'):
            return api_response(data=result)
        else:
            status_code = 400
            if result.get('skipped'):
                status_code = 200  # 跳过不算错误
            
            return api_response(
                error=result.get('error', '写入失败'),
                status=status_code
            )
    
    except KeyError as e:
        return api_response(error=f'缺少必需参数: {str(e)}', status=400)
    except Exception as e:
        logger.exception("从结果写入补偿值失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def batch_write_for_recipe(request):
    """
    批量写入配方所有层的补偿值
    
    请求体:
    {
        "recipe_id": 1,
        "layers": [1, 2, 3],  // 可选
        "validate": true
    }
    """
    try:
        data = json.loads(request.body)
        
        result = plc_writer.batch_write_compensations_for_recipe(
            recipe_id=data['recipe_id'],
            layers=data.get('layers'),
            validate=data.get('validate', True)
        )
        
        return api_response(data=result)
    
    except KeyError as e:
        return api_response(error=f'缺少必需参数: {str(e)}', status=400)
    except Exception as e:
        logger.exception("批量写入补偿值失败")
        return api_response(error=str(e), status=500)


# ========== 完整流程接口 ==========

@csrf_exempt
@require_http_methods(["POST"])
def complete_positioning_and_write(request):
    """
    完整流程：定位 → 补偿计算 → PLC写入
    
    请求体:
    {
        "recipe_id": 1,
        "layer_no": 2,
        "pointcloud": {...},  // 或 "pointcloud_file": "path"
        "coordinate_system": "ROBOT",
        "rack_side": "BOTH",
        "validate": true,
        "write_to_plc": true
    }
    """
    try:
        from .rack_positioning_service import RackPositioningService
        from .compensation_service import CompensationService
        
        data = json.loads(request.body)
        
        # 步骤1: 执行定位
        positioning_service = RackPositioningService()
        
        # 获取点云数据
        if 'pointcloud' in data:
            pointcloud = data['pointcloud']
        elif 'pointcloud_file' in data:
            import numpy as np
            pointcloud = np.load(data['pointcloud_file'])
        else:
            return api_response(error='缺少点云数据', status=400)
        
        positioning_result = positioning_service.process_layer_positioning(
            recipe_id=data['recipe_id'],
            layer_no=data['layer_no'],
            pointcloud=pointcloud,
            coordinate_system=data.get('coordinate_system', 'ROBOT'),
            vision_task_id=data.get('vision_task_id')
        )
        
        response_data = {
            'positioning_success': positioning_result.is_success,
            'positioning_result': {
                'offset_x': positioning_result.offset_x,
                'offset_y': positioning_result.offset_y,
                'offset_z': positioning_result.offset_z,
                'confidence_x': positioning_result.confidence_x,
                'confidence_y': positioning_result.confidence_y,
                'confidence_z': positioning_result.confidence_z
            }
        }
        
        if not positioning_result.is_success:
            response_data['message'] = '定位失败'
            return api_response(data=response_data)
        
        # 步骤2: 计算补偿值
        compensation_service = CompensationService()
        
        compensation = compensation_service.calculate_compensation_from_positioning_result(
            positioning_result=positioning_result,
            rack_side=data.get('rack_side', 'BOTH')
        )
        
        response_data['compensation_success'] = compensation.is_valid
        response_data['compensation'] = {
            'compensation_x': compensation.compensation_x,
            'compensation_y': compensation.compensation_y,
            'compensation_z': compensation.compensation_z,
            'is_valid': compensation.is_valid,
            'validation_message': compensation.validation_message
        }
        
        # 步骤3: 写入PLC（如果需要）
        if data.get('write_to_plc', True) and compensation.is_valid:
            write_result = plc_writer.write_compensation_to_plc(
                compensation=compensation,
                layer_no=data['layer_no'],
                position_no=data.get('position_no'),
                rack_side=data.get('rack_side', 'BOTH'),
                recipe_id=data['recipe_id'],
                validate=data.get('validate', True)
            )
            
            response_data['plc_write_success'] = write_result.get('success')
            response_data['plc_write_result'] = write_result
        else:
            response_data['plc_write_success'] = False
            response_data['plc_write_result'] = {
                'skipped': True,
                'reason': '补偿值无效或未启用PLC写入'
            }
        
        # 判断整体成功
        overall_success = (
            positioning_result.is_success and
            compensation.is_valid and
            (response_data.get('plc_write_success') or not data.get('write_to_plc', True))
        )
        
        response_data['overall_success'] = overall_success
        response_data['message'] = '完整流程执行成功' if overall_success else '流程执行失败'
        
        return api_response(data=response_data)
    
    except KeyError as e:
        return api_response(error=f'缺少必需参数: {str(e)}', status=400)
    except Exception as e:
        logger.exception("完整流程执行失败")
        return api_response(error=str(e), status=500)


# ========== 查询接口 ==========

@require_http_methods(["GET"])
def get_plc_write_status(request):
    """
    查询PLC写入状态
    
    Query参数:
    - result_id: 结果ID（必需）
    """
    try:
        from .models import RackLocationResult
        
        result_id = request.GET.get('result_id')
        
        if not result_id:
            return api_response(error='缺少result_id参数', status=400)
        
        result = RackLocationResult.objects.get(id=result_id)
        
        status_data = {
            'result_id': result.id,
            'plc_write_status': result.plc_write_status,
            'plc_error_message': result.plc_error_message,
            'plc_written_at': result.plc_written_at.isoformat() if result.plc_written_at else None,
            'plc_payload': result.result_data.get('plc_payload') if result.result_data else None
        }
        
        return api_response(data=status_data)
    
    except RackLocationResult.DoesNotExist:
        return api_response(error='结果不存在', status=404)
    except Exception as e:
        logger.exception("查询PLC写入状态失败")
        return api_response(error=str(e), status=500)


@require_http_methods(["GET"])
def get_plc_write_history(request):
    """
    查询PLC写入历史
    
    Query参数:
    - recipe_id: 配方ID（必需）
    - layer_no: 层号（可选）
    - limit: 返回数量（默认10）
    """
    try:
        from .models import RackLocationResult
        
        recipe_id = request.GET.get('recipe_id')
        
        if not recipe_id:
            return api_response(error='缺少recipe_id参数', status=400)
        
        layer_no = request.GET.get('layer_no')
        limit = int(request.GET.get('limit', 10))
        
        # 构建查询
        query = RackLocationResult.objects.filter(
            recipe_id=recipe_id,
            plc_write_status__isnull=False
        )
        
        if layer_no:
            query = query.filter(layer_no=layer_no)
        
        results = query.order_by('-plc_written_at')[:limit]
        
        history = []
        for result in results:
            history.append({
                'result_id': result.id,
                'layer_no': result.layer_no,
                'position_no': result.position_no,
                'plc_write_status': result.plc_write_status,
                'plc_error_message': result.plc_error_message,
                'plc_written_at': result.plc_written_at.isoformat() if result.plc_written_at else None,
                'offset_x': float(result.offset_x),
                'offset_y': float(result.offset_y),
                'offset_z': float(result.offset_z),
                'compensation': result.result_data.get('compensation') if result.result_data else None
            })
        
        return api_response(data={
            'history': history,
            'total': len(history)
        })
    
    except Exception as e:
        logger.exception("查询PLC写入历史失败")
        return api_response(error=str(e), status=500)
