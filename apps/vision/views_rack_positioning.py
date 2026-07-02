"""
料架定位算法模块 API视图
"""
import json
import logging
import numpy as np
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .rack_positioning_service import RackPositioningService
from .rack_positioning_algorithm import RackPositioningAlgorithm

logger = logging.getLogger(__name__)

# 初始化服务
positioning_service = RackPositioningService()
positioning_algorithm = RackPositioningAlgorithm()


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


# ========== 定位计算接口 ==========

@csrf_exempt
@require_http_methods(["POST"])
def process_positioning(request):
    """
    处理料架定位（完整流程）
    
    请求体:
    {
        "recipe_id": 1,
        "layer_no": 2,
        "pointcloud": [[x1,y1,z1], [x2,y2,z2], ...],  // 点云数据
        "coordinate_system": "ROBOT",  // 或 "CAMERA"
        "robot_pose": [x, y, z, rx, ry, rz],  // 可选，相机坐标系时需要
        "vision_task_id": 123,  // 可选，用于保存结果
        "rack_id": 456,  // 可选
        "algorithm_params": {  // 可选
            "plane_params": {...},
            "edge_params": {...},
            "pillar_params": {...}
        }
    }
    """
    try:
        data = json.loads(request.body)
        
        # 解析点云
        pointcloud_list = data.get('pointcloud')
        if not pointcloud_list:
            return api_response(error='缺少pointcloud参数', status=400)
        
        pointcloud = np.array(pointcloud_list, dtype=np.float32)
        
        if pointcloud.shape[1] != 3:
            return api_response(error='点云格式错误，应为 (N, 3)', status=400)
        
        # 解析robot_pose（如果有）
        robot_pose = None
        if 'robot_pose' in data:
            robot_pose = np.array(data['robot_pose'], dtype=np.float32)
        
        # 执行定位
        result = positioning_service.process_layer_positioning(
            recipe_id=data['recipe_id'],
            layer_no=data['layer_no'],
            pointcloud=pointcloud,
            robot_pose=robot_pose,
            coordinate_system=data.get('coordinate_system', 'ROBOT'),
            vision_task_id=data.get('vision_task_id'),
            rack_id=data.get('rack_id'),
            algorithm_params=data.get('algorithm_params')
        )
        
        # 转换为字典
        result_dict = positioning_algorithm.to_dict(result)
        
        return api_response(data={
            'positioning_result': result_dict,
            'message': '定位完成' if result.is_success else '定位失败'
        })
    
    except KeyError as e:
        return api_response(error=f'缺少必需参数: {str(e)}', status=400)
    except Exception as e:
        logger.exception("处理定位请求失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def detect_plane(request):
    """
    单独检测平面（找Z）
    
    请求体:
    {
        "pointcloud": [[x1,y1,z1], ...],
        "distance_threshold": 2.0,
        "min_inliers": 100
    }
    """
    try:
        data = json.loads(request.body)
        
        pointcloud = np.array(data['pointcloud'], dtype=np.float32)
        
        result = positioning_algorithm.detect_support_plane(
            pointcloud=pointcloud,
            distance_threshold=data.get('distance_threshold', 2.0),
            min_inliers=data.get('min_inliers', 100)
        )
        
        return api_response(data={
            'z_position': result.z_position,
            'z_std': result.z_std,
            'inliers_count': int(result.inliers.shape[0]),
            'confidence': result.confidence,
            'plane_model': result.plane_model.tolist()
        })
    
    except Exception as e:
        logger.exception("平面检测失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def detect_edge(request):
    """
    单独检测前边缘（找Y）
    
    请求体:
    {
        "pointcloud": [[x1,y1,z1], ...],
        "gradient_threshold": 50.0,
        "min_edge_points": 50
    }
    """
    try:
        data = json.loads(request.body)
        
        pointcloud = np.array(data['pointcloud'], dtype=np.float32)
        
        result = positioning_algorithm.detect_front_edge(
            pointcloud=pointcloud,
            gradient_threshold=data.get('gradient_threshold', 50.0),
            min_edge_points=data.get('min_edge_points', 50)
        )
        
        return api_response(data={
            'y_position': result.y_position,
            'y_std': result.y_std,
            'edge_points_count': int(result.edge_points.shape[0]),
            'confidence': result.confidence
        })
    
    except Exception as e:
        logger.exception("边缘检测失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def detect_pillar(request):
    """
    单独检测立柱（找X）
    
    请求体:
    {
        "pointcloud": [[x1,y1,z1], ...],
        "vertical_tolerance": 10.0,
        "min_pillar_points": 50
    }
    """
    try:
        data = json.loads(request.body)
        
        pointcloud = np.array(data['pointcloud'], dtype=np.float32)
        
        result = positioning_algorithm.detect_pillar(
            pointcloud=pointcloud,
            vertical_tolerance=data.get('vertical_tolerance', 10.0),
            min_pillar_points=data.get('min_pillar_points', 50)
        )
        
        return api_response(data={
            'x_position': result.x_position,
            'x_std': result.x_std,
            'pillar_points_count': int(result.pillar_points.shape[0]),
            'confidence': result.confidence
        })
    
    except Exception as e:
        logger.exception("立柱检测失败")
        return api_response(error=str(e), status=500)


# ========== 历史记录接口 ==========

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


# ========== 算法参数接口 ==========

@require_http_methods(["GET"])
def get_default_algorithm_params(request):
    """获取默认算法参数"""
    try:
        default_params = {
            'plane_params': {
                'distance_threshold': 2.0,
                'ransac_n': 3,
                'num_iterations': 1000,
                'min_inliers': 100,
                'description': '平面检测参数（RANSAC）'
            },
            'edge_params': {
                'gradient_threshold': 50.0,
                'min_edge_points': 50,
                'bin_size': 5.0,
                'description': '边缘检测参数（梯度法）'
            },
            'pillar_params': {
                'vertical_tolerance': 10.0,
                'min_pillar_points': 50,
                'bin_size': 5.0,
                'description': '立柱检测参数（垂直度检测）'
            }
        }
        
        return api_response(data=default_params)
    
    except Exception as e:
        logger.exception("获取默认参数失败")
        return api_response(error=str(e), status=500)
