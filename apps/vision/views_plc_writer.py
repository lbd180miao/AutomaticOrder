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
        "compensation_x2": 1.0,
        "compensation_y2": 2.0,
        "compensation_z2": 3.0,
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
            validate=data.get('validate', True),
            second_group={axis: data[f'compensation_{axis}2'] for axis in 'xyz'
                          if f'compensation_{axis}2' in data},
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
    """Calculate with the cloud template and retain its PLC publication gate."""
    try:
        from .rack_location import RackLocationService, PlcVisionResultWriter
        from .models import RackLocationResult
        data = json.loads(request.body)
        payload = RackLocationService().calculate_workbench(
            token=data['pointcloud_token'], recipe_id=data['recipe_id'],
            layer_no=int(data.get('layer_no', 1)), save_record=True,
        )
        response = {'positioning_success': payload['locate_ok'], 'positioning_result': payload,
                    'plc_write_success': False}
        if data.get('write_to_plc', True):
            record = RackLocationResult.objects.get(pk=payload['result_id'])
            written = PlcVisionResultWriter().write(record)
            response.update(plc_write_success=written.get('success', False), plc_write_result=written)
        return api_response(data=response)
    except (KeyError, TypeError, ValueError) as exc:
        return api_response(error=str(exc), status=400)


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
            'plc_written_at': (result.result_data or {}).get('plc_written_at'),
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
        
        results = query.order_by('-result_data__plc_written_at')[:limit]
        
        history = []
        for result in results:
            history.append({
                'result_id': result.id,
                'layer_no': result.layer_no,
                'position_no': result.position_no,
                'plc_write_status': result.plc_write_status,
                'plc_error_message': result.plc_error_message,
                'plc_written_at': (result.result_data or {}).get('plc_written_at'),
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
