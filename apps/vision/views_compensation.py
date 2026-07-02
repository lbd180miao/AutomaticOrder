"""
补偿值计算模块 API视图
"""
import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .compensation_service import CompensationService
from .compensation_calculator import CompensationRule, OffsetData
from apps.core.constants import RackSide

logger = logging.getLogger(__name__)

# 初始化服务
compensation_service = CompensationService()


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


# ========== 补偿值计算接口 ==========

@csrf_exempt
@require_http_methods(["POST"])
def calculate_compensation(request):
    """
    计算补偿值
    
    请求体:
    {
        "offset_x": -2.23,
        "offset_y": 4.60,
        "offset_z": 2.05,
        "confidence_x": 1.0,
        "confidence_y": 1.0,
        "confidence_z": 0.624,
        "rack_side": "BOTH",  // LEFT/RIGHT/BOTH
        "offset_rz": 0.0
    }
    """
    try:
        data = json.loads(request.body)
        
        # 创建偏移值数据
        offset_data = OffsetData(
            offset_x=data['offset_x'],
            offset_y=data['offset_y'],
            offset_z=data['offset_z'],
            confidence_x=data.get('confidence_x', 1.0),
            confidence_y=data.get('confidence_y', 1.0),
            confidence_z=data.get('confidence_z', 1.0)
        )
        
        # 计算补偿值
        compensation = compensation_service.calculator.calculate_compensation_from_offset_data(
            offset_data=offset_data,
            rack_side=data.get('rack_side', RackSide.BOTH),
            offset_rz=data.get('offset_rz', 0.0)
        )
        
        # 转换为字典
        result = compensation_service.calculator.to_dict(compensation)
        
        # 准备PLC数据
        plc_data = compensation_service.calculator.to_plc_format(compensation)
        
        return api_response(data={
            'compensation': result,
            'plc_data': plc_data,
            'message': '补偿值计算完成' if compensation.is_valid else '补偿值验证失败'
        })
    
    except KeyError as e:
        return api_response(error=f'缺少必需参数: {str(e)}', status=400)
    except Exception as e:
        logger.exception("计算补偿值失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def calculate_from_result(request):
    """
    从定位结果计算补偿值
    
    请求体:
    {
        "result_id": 123,
        "rack_side": "BOTH",  // 可选
        "offset_rz": 0.0,     // 可选
        "save_to_result": true  // 是否保存到结果记录
    }
    """
    try:
        data = json.loads(request.body)
        
        compensation = compensation_service.calculate_and_save_compensation(
            result_id=data['result_id'],
            rack_side=data.get('rack_side'),
            offset_rz=data.get('offset_rz', 0.0),
            save_to_result=data.get('save_to_result', True)
        )
        
        result = compensation_service.calculator.to_dict(compensation)
        plc_data = compensation_service.calculator.to_plc_format(compensation)
        
        return api_response(data={
            'compensation': result,
            'plc_data': plc_data,
            'message': '补偿值已计算并保存' if data.get('save_to_result', True) else '补偿值已计算'
        })
    
    except KeyError as e:
        return api_response(error=f'缺少必需参数: {str(e)}', status=400)
    except Exception as e:
        logger.exception("从结果计算补偿值失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def batch_calculate(request):
    """
    批量计算配方所有层的补偿值
    
    请求体:
    {
        "recipe_id": 1,
        "layers": [1, 2, 3]  // 可选，默认为所有层
    }
    """
    try:
        data = json.loads(request.body)
        
        compensations = compensation_service.batch_calculate_compensations_for_recipe(
            recipe_id=data['recipe_id'],
            layers=data.get('layers')
        )
        
        # 转换为字典
        result = {}
        for layer_no, compensation in compensations.items():
            result[str(layer_no)] = compensation_service.calculator.to_dict(compensation)
        
        return api_response(data={
            'compensations': result,
            'total': len(result),
            'message': f'批量计算完成，共{len(result)}个层'
        })
    
    except KeyError as e:
        return api_response(error=f'缺少必需参数: {str(e)}', status=400)
    except Exception as e:
        logger.exception("批量计算补偿值失败")
        return api_response(error=str(e), status=500)


# ========== 补偿值查询接口 ==========

@require_http_methods(["GET"])
def get_compensation(request):
    """
    获取补偿值
    
    Query参数:
    - result_id: 结果ID（必需）
    """
    try:
        result_id = request.GET.get('result_id')
        
        if not result_id:
            return api_response(error='缺少result_id参数', status=400)
        
        compensation = compensation_service.get_compensation_from_result(int(result_id))
        
        if compensation is None:
            return api_response(error='未找到补偿值', status=404)
        
        return api_response(data={'compensation': compensation})
    
    except Exception as e:
        logger.exception("获取补偿值失败")
        return api_response(error=str(e), status=500)


@require_http_methods(["GET"])
def get_latest_compensation(request):
    """
    获取最新补偿值
    
    Query参数:
    - recipe_id: 配方ID（必需）
    - layer_no: 层号（必需）
    - limit: 返回数量（默认1）
    """
    try:
        recipe_id = request.GET.get('recipe_id')
        layer_no = request.GET.get('layer_no')
        
        if not recipe_id or not layer_no:
            return api_response(error='缺少recipe_id或layer_no参数', status=400)
        
        limit = int(request.GET.get('limit', 1))
        
        compensations = compensation_service.get_latest_compensation(
            recipe_id=int(recipe_id),
            layer_no=int(layer_no),
            limit=limit
        )
        
        return api_response(data={
            'compensations': compensations,
            'total': len(compensations)
        })
    
    except Exception as e:
        logger.exception("获取最新补偿值失败")
        return api_response(error=str(e), status=500)


@require_http_methods(["GET"])
def get_average_compensation(request):
    """
    获取平均补偿值
    
    Query参数:
    - recipe_id: 配方ID（必需）
    - layer_no: 层号（必需）
    - count: 统计数量（默认10）
    """
    try:
        recipe_id = request.GET.get('recipe_id')
        layer_no = request.GET.get('layer_no')
        
        if not recipe_id or not layer_no:
            return api_response(error='缺少recipe_id或layer_no参数', status=400)
        
        count = int(request.GET.get('count', 10))
        
        avg_compensation = compensation_service.get_average_compensation(
            recipe_id=int(recipe_id),
            layer_no=int(layer_no),
            count=count
        )
        
        return api_response(data=avg_compensation)
    
    except Exception as e:
        logger.exception("获取平均补偿值失败")
        return api_response(error=str(e), status=500)


# ========== 补偿值统计接口 ==========

@require_http_methods(["GET"])
def get_statistics(request):
    """
    获取补偿值统计
    
    Query参数:
    - recipe_id: 配方ID（必需）
    - layer_no: 层号（必需）
    - count: 统计数量（默认20）
    """
    try:
        recipe_id = request.GET.get('recipe_id')
        layer_no = request.GET.get('layer_no')
        
        if not recipe_id or not layer_no:
            return api_response(error='缺少recipe_id或layer_no参数', status=400)
        
        count = int(request.GET.get('count', 20))
        
        statistics = compensation_service.get_compensation_statistics(
            recipe_id=int(recipe_id),
            layer_no=int(layer_no),
            count=count
        )
        
        return api_response(data=statistics)
    
    except Exception as e:
        logger.exception("获取补偿值统计失败")
        return api_response(error=str(e), status=500)


# ========== PLC数据接口 ==========

@csrf_exempt
@require_http_methods(["POST"])
def prepare_plc_data(request):
    """
    准备PLC数据
    
    请求体:
    {
        "result_id": 123,
        "layer_no": 2,
        "additional_data": {}  // 可选
    }
    """
    try:
        data = json.loads(request.body)
        
        # 获取补偿值
        compensation_dict = compensation_service.get_compensation_from_result(data['result_id'])
        
        if not compensation_dict:
            return api_response(error='未找到补偿值', status=404)
        
        # 重建CompensationData对象
        from .compensation_calculator import CompensationData
        compensation = CompensationData(
            compensation_x=compensation_dict['compensation_x'],
            compensation_y=compensation_dict['compensation_y'],
            compensation_z=compensation_dict['compensation_z'],
            compensation_rz=compensation_dict.get('compensation_rz', 0.0),
            confidence_x=compensation_dict['confidence_x'],
            confidence_y=compensation_dict['confidence_y'],
            confidence_z=compensation_dict['confidence_z'],
            is_valid=compensation_dict['is_valid'],
            validation_message=compensation_dict.get('validation_message', '')
        )
        
        # 准备PLC数据
        plc_data = compensation_service.prepare_plc_data(
            compensation=compensation,
            layer_no=data['layer_no'],
            additional_data=data.get('additional_data')
        )
        
        return api_response(data={
            'plc_data': plc_data,
            'message': 'PLC数据已准备'
        })
    
    except KeyError as e:
        return api_response(error=f'缺少必需参数: {str(e)}', status=400)
    except Exception as e:
        logger.exception("准备PLC数据失败")
        return api_response(error=str(e), status=500)


# ========== 配置接口 ==========

@require_http_methods(["GET"])
def get_default_rule(request):
    """获取默认补偿规则"""
    try:
        rule = CompensationRule()
        
        rule_dict = {
            'x_direction': rule.x_direction,
            'y_direction': rule.y_direction,
            'z_direction': rule.z_direction,
            'max_compensation_x': rule.max_compensation_x,
            'max_compensation_y': rule.max_compensation_y,
            'max_compensation_z': rule.max_compensation_z,
            'max_compensation_rz': rule.max_compensation_rz,
            'min_confidence': rule.min_confidence,
            'left_side_x_invert': rule.left_side_x_invert,
            'right_side_x_invert': rule.right_side_x_invert
        }
        
        return api_response(data={'rule': rule_dict})
    
    except Exception as e:
        logger.exception("获取默认规则失败")
        return api_response(error=str(e), status=500)
