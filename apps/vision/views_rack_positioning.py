"""Read-only history of rack positioning measurements."""
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .rack_position_history import RackPositionHistory
logger = logging.getLogger(__name__)
positioning_service = RackPositionHistory()

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


@require_http_methods(["GET"])
def get_positioning_history(request):
    """
    获取定位历史记录
    
    Query参数:
    - recipe_id: 配方ID（必需）
    - layer_no: 层号（可选）
    - limit: 返回数量（默认10）
    """
    try:
        recipe_id = request.GET.get('recipe_id')
        if not recipe_id:
            return api_response(error='缺少recipe_id参数', status=400)
        
        layer_no = request.GET.get('layer_no')
        limit = int(request.GET.get('limit', 10))
        
        results = positioning_service.get_positioning_history(
            recipe_id=int(recipe_id),
            layer_no=int(layer_no) if layer_no else None,
            limit=limit
        )
        
        # 转换为字典列表
        history = [{
            'id': r.id,
            'layer_no': r.layer_no,
            'offset_x': float(r.offset_x),
            'offset_y': float(r.offset_y),
            'offset_z': float(r.offset_z),
            'actual_x': float(r.actual_x),
            'actual_y': float(r.actual_y),
            'actual_z': float(r.actual_z),
            'confidence': float(r.confidence),
            'is_success': r.is_success,
            'error_message': r.error_message,
            'created_at': r.created_at.isoformat(),
            'result_data': r.result_data
        } for r in results]
        
        return api_response(data={
            'history': history,
            'total': len(history)
        })
    
    except Exception as e:
        logger.exception("获取历史记录失败")
        return api_response(error=str(e), status=500)


@require_http_methods(["GET"])
def get_average_offsets(request):
    """
    获取平均偏移值
    
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
        
        avg_offsets = positioning_service.get_average_offsets(
            recipe_id=int(recipe_id),
            layer_no=int(layer_no),
            count=count
        )
        
        return api_response(data=avg_offsets)
    
    except Exception as e:
        logger.exception("获取平均偏移失败")
        return api_response(error=str(e), status=500)


@require_http_methods(["GET"])
def analyze_stability(request):
    """
    分析定位稳定性
    
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
        
        stability = positioning_service.analyze_positioning_stability(
            recipe_id=int(recipe_id),
            layer_no=int(layer_no),
            count=count
        )
        
        return api_response(data=stability)
    
    except Exception as e:
        logger.exception("分析稳定性失败")
        return api_response(error=str(e), status=500)
