"""
3D ROI配方模块 API视图
"""
import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from .models_3d_roi import RackLocationROI3DEnhanced, ROI3DTemplate, ROI3DType
from .roi_3d_service import ROI3DService

logger = logging.getLogger(__name__)

# 初始化服务
roi_service = ROI3DService()


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


# ========== ROI CRUD ==========

@require_http_methods(["GET"])
def list_rois(request):
    """获取ROI列表"""
    try:
        recipe_id = request.GET.get('recipe_id')
        layer_no = request.GET.get('layer_no')
        roi_type = request.GET.get('roi_type')
        enabled_only = request.GET.get('enabled_only', 'true').lower() == 'true'
        
        if not recipe_id:
            return api_response(error='缺少recipe_id参数', status=400)
        
        if layer_no:
            rois = roi_service.get_rois_by_layer(
                int(recipe_id),
                int(layer_no),
                roi_type,
                enabled_only
            )
        elif roi_type:
            rois = roi_service.get_rois_by_type(
                int(recipe_id),
                roi_type,
                enabled_only
            )
        else:
            # 获取所有ROI
            queryset = RackLocationROI3DEnhanced.objects.filter(recipe_id=recipe_id)
            if enabled_only:
                queryset = queryset.filter(enabled=True)
            rois = list(queryset)
        
        result = [roi.to_dict() for roi in rois]
        
        return api_response(data={
            'rois': result,
            'total': len(result)
        })
    
    except Exception as e:
        logger.exception("获取ROI列表失败")
        return api_response(error=str(e), status=500)


@require_http_methods(["GET"])
def get_roi(request, roi_id):
    """获取ROI详情"""
    try:
        roi = get_object_or_404(RackLocationROI3DEnhanced, id=roi_id)
        return api_response(data=roi.to_dict())
    
    except Exception as e:
        logger.exception("获取ROI详情失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def create_roi(request):
    """创建ROI"""
    try:
        data = json.loads(request.body)
        
        roi = roi_service.create_roi(
            recipe_id=data['recipe_id'],
            roi_name=data['roi_name'],
            roi_type=data['roi_type'],
            layer_no=data['layer_no'],
            x_min=data['x_min'],
            x_max=data['x_max'],
            y_min=data['y_min'],
            y_max=data['y_max'],
            z_min=data['z_min'],
            z_max=data['z_max'],
            position_no=data.get('position_no', 1),
            coordinate_system=data.get('coordinate_system', 'ROBOT'),
            priority=data.get('priority', 100),
            weight=data.get('weight', 1.0),
            algorithm_params=data.get('algorithm_params'),
            description=data.get('description', '')
        )
        
        return api_response(data={
            'id': roi.id,
            'roi': roi.to_dict(),
            'message': f'ROI {roi.roi_name} 创建成功'
        })
    
    except KeyError as e:
        return api_response(error=f'缺少必需参数: {str(e)}', status=400)
    except Exception as e:
        logger.exception("创建ROI失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
def update_roi(request, roi_id):
    """更新ROI"""
    try:
        data = json.loads(request.body)
        
        roi = roi_service.update_roi(roi_id, **data)
        
        return api_response(data={
            'roi': roi.to_dict(),
            'message': 'ROI更新成功'
        })
    
    except Exception as e:
        logger.exception("更新ROI失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_roi(request, roi_id):
    """删除ROI"""
    try:
        success = roi_service.delete_roi(roi_id)
        
        if success:
            return api_response(data={'message': 'ROI删除成功'})
        else:
            return api_response(error='ROI不存在', status=404)
    
    except Exception as e:
        logger.exception("删除ROI失败")
        return api_response(error=str(e), status=500)


# ========== 层级管理 ==========

@require_http_methods(["GET"])
def get_layer_summary(request):
    """获取指定层的ROI汇总"""
    try:
        recipe_id = request.GET.get('recipe_id')
        layer_no = request.GET.get('layer_no')
        
        if not recipe_id or not layer_no:
            return api_response(error='缺少recipe_id或layer_no参数', status=400)
        
        summary = roi_service.get_layer_roi_summary(int(recipe_id), int(layer_no))
        
        # 转换为可序列化格式
        result = {
            'layer_no': summary['layer_no'],
            'total_rois': summary['total_rois'],
            'main_roi': summary['main_roi'].to_dict() if summary['main_roi'] else None,
            'support_plane_rois': [roi.to_dict() for roi in summary['support_plane_rois']],
            'front_edge_rois': [roi.to_dict() for roi in summary['front_edge_rois']],
            'pillar_rois': [roi.to_dict() for roi in summary['pillar_rois']],
            'side_edge_rois': [roi.to_dict() for roi in summary['side_edge_rois']],
            'other_rois': [roi.to_dict() for roi in summary['other_rois']],
        }
        
        return api_response(data=result)
    
    except Exception as e:
        logger.exception("获取层ROI汇总失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def batch_create_layer_rois(request):
    """批量创建一层的标准ROI"""
    try:
        data = json.loads(request.body)
        
        created_rois = roi_service.batch_create_layer_rois(
            recipe_id=data['recipe_id'],
            layer_no=data['layer_no'],
            position_no=data.get('position_no', 1)
        )
        
        result = {
            key: roi.to_dict()
            for key, roi in created_rois.items()
        }
        
        return api_response(data={
            'rois': result,
            'message': f'第{data["layer_no"]}层的4种标准ROI创建成功'
        })
    
    except KeyError as e:
        return api_response(error=f'缺少必需参数: {str(e)}', status=400)
    except Exception as e:
        logger.exception("批量创建层ROI失败")
        return api_response(error=str(e), status=500)


# ========== 模板管理 ==========

@require_http_methods(["GET"])
def list_templates(request):
    """获取模板列表"""
    try:
        rack_type = request.GET.get('rack_type')
        active_only = request.GET.get('active_only', 'true').lower() == 'true'
        
        if rack_type:
            templates = roi_service.get_templates_by_rack_type(rack_type, active_only)
        else:
            queryset = ROI3DTemplate.objects.all()
            if active_only:
                queryset = queryset.filter(is_active=True)
            templates = list(queryset)
        
        result = [{
            'id': t.id,
            'template_name': t.template_name,
            'rack_type': t.rack_type,
            'layer_count': t.layer_count,
            'roi_count': len(t.roi_configs),
            'is_active': t.is_active,
            'description': t.description,
            'created_at': t.created_at.isoformat(),
        } for t in templates]
        
        return api_response(data={
            'templates': result,
            'total': len(result)
        })
    
    except Exception as e:
        logger.exception("获取模板列表失败")
        return api_response(error=str(e), status=500)


@require_http_methods(["GET"])
def get_template(request, template_id):
    """获取模板详情"""
    try:
        template = get_object_or_404(ROI3DTemplate, id=template_id)
        
        result = {
            'id': template.id,
            'template_name': template.template_name,
            'rack_type': template.rack_type,
            'layer_count': template.layer_count,
            'roi_configs': template.roi_configs,
            'default_algorithm_params': template.default_algorithm_params,
            'is_active': template.is_active,
            'description': template.description,
            'created_at': template.created_at.isoformat(),
            'updated_at': template.updated_at.isoformat(),
        }
        
        return api_response(data=result)
    
    except Exception as e:
        logger.exception("获取模板详情失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def create_template(request):
    """创建模板"""
    try:
        data = json.loads(request.body)
        
        template = roi_service.create_template(
            template_name=data['template_name'],
            rack_type=data['rack_type'],
            layer_count=data['layer_count'],
            roi_configs=data['roi_configs'],
            default_algorithm_params=data.get('default_algorithm_params'),
            description=data.get('description', '')
        )
        
        return api_response(data={
            'id': template.id,
            'message': f'模板 {template.template_name} 创建成功'
        })
    
    except KeyError as e:
        return api_response(error=f'缺少必需参数: {str(e)}', status=400)
    except Exception as e:
        logger.exception("创建模板失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def apply_template(request):
    """应用模板到配方"""
    try:
        data = json.loads(request.body)
        
        created_rois = roi_service.apply_template(
            template_id=data['template_id'],
            recipe_id=data['recipe_id'],
            clear_existing=data.get('clear_existing', False)
        )
        
        result = [roi.to_dict() for roi in created_rois]
        
        return api_response(data={
            'rois': result,
            'total': len(result),
            'message': f'模板应用成功，创建了 {len(result)} 个ROI'
        })
    
    except KeyError as e:
        return api_response(error=f'缺少必需参数: {str(e)}', status=400)
    except Exception as e:
        logger.exception("应用模板失败")
        return api_response(error=str(e), status=500)


# ========== 统计和分析 ==========

@require_http_methods(["GET"])
def get_recipe_statistics(request):
    """获取配方的ROI统计"""
    try:
        recipe_id = request.GET.get('recipe_id')
        
        if not recipe_id:
            return api_response(error='缺少recipe_id参数', status=400)
        
        stats = roi_service.get_recipe_roi_statistics(int(recipe_id))
        
        return api_response(data=stats)
    
    except Exception as e:
        logger.exception("获取ROI统计失败")
        return api_response(error=str(e), status=500)


@require_http_methods(["GET"])
def get_roi_types(request):
    """获取所有ROI类型"""
    try:
        types = [
            {
                'value': roi_type.value,
                'label': roi_type.label,
                'description': get_roi_type_description(roi_type.value)
            }
            for roi_type in ROI3DType
        ]
        
        return api_response(data={'types': types})
    
    except Exception as e:
        logger.exception("获取ROI类型失败")
        return api_response(error=str(e), status=500)


def get_roi_type_description(roi_type: str) -> str:
    """获取ROI类型的详细说明"""
    descriptions = {
        'MAIN': '当前层整体定位区域，用于初步定位和整体点云提取',
        'SUPPORT_PLANE': '支撑面区域，用于平面拟合，计算Z轴偏移',
        'FRONT_EDGE': '前边缘区域，用于边缘检测，计算Y轴偏移',
        'PILLAR': '立柱区域，用于检测侧边/立柱，计算X轴偏移',
        'SIDE_EDGE': '侧边缘区域，用于侧边检测，辅助X轴定位',
        'CUSTOM': '自定义ROI，用于特殊用途'
    }
    return descriptions.get(roi_type, '')


# ========== 配方管理API ==========

@require_http_methods(["GET"])
def list_recipes(request):
    """获取配方列表"""
    try:
        from .models import RackLocationRecipe
        
        recipes = RackLocationRecipe.objects.all().order_by('-created_at')
        
        result = [{
            'id': r.id,
            'recipe_name': r.recipe_name,
            'rack_type': r.rack_type,
            'layer_count': r.layer_count,
            'position_no': r.position_no,
            'enabled': r.enabled,
        } for r in recipes]
        
        return api_response(data={'recipes': result, 'total': len(result)})
    
    except Exception as e:
        logger.exception("获取配方列表失败")
        return api_response(error=str(e), status=500)


@require_http_methods(["GET"])
def get_recipe_detail(request, recipe_id):
    """获取配方详情"""
    try:
        from .models import RackLocationRecipe
        
        recipe = get_object_or_404(RackLocationRecipe, id=recipe_id)
        
        result = {
            'id': recipe.id,
            'recipe_name': recipe.recipe_name,
            'rack_type': recipe.rack_type,
            'rack_side': recipe.rack_side,
            'position_no': recipe.position_no,
            'layer_count': recipe.layer_count,
            'layer_no': recipe.layer_no,
            'standard_x': float(recipe.standard_x),
            'standard_y': float(recipe.standard_y),
            'standard_z': float(recipe.standard_z),
            'standard_rz': float(recipe.standard_rz),
            'enabled': recipe.enabled,
        }
        
        return api_response(data={'recipe': result})
    
    except Exception as e:
        logger.exception("获取配方详情失败")
        return api_response(error=str(e), status=500)




# ========== 工作台专用API ==========

@csrf_exempt
@require_http_methods(["POST"])
def auto_fill_roi(request):
    """自动填充ROI参数（基于点云边界）"""
    try:
        data = json.loads(request.body)
        
        recipe_id = data.get('recipe_id')
        layer_no = data.get('layer_no')
        roi_type = data.get('roi_type', 'MAIN')
        pointcloud = data.get('pointcloud')
        
        if not pointcloud:
            return api_response(error='缺少点云数据', status=400)
        
        # 计算点云边界
        import numpy as np
        points = np.array(pointcloud.get('points', []))
        
        if len(points) == 0:
            return api_response(error='点云为空', status=400)
        
        # 计算边界（留10%边距）
        margin = 0.1
        x_min, x_max = points[:, 0].min(), points[:, 0].max()
        y_min, y_max = points[:, 1].min(), points[:, 1].max()
        z_min, z_max = points[:, 2].min(), points[:, 2].max()
        
        x_range = x_max - x_min
        y_range = y_max - y_min
        z_range = z_max - z_min
        
        roi = {
            'x_min': float(x_min - x_range * margin),
            'x_max': float(x_max + x_range * margin),
            'y_min': float(y_min - y_range * margin),
            'y_max': float(y_max + y_range * margin),
            'z_min': float(z_min - z_range * margin),
            'z_max': float(z_max + z_range * margin),
        }
        
        # 根据ROI类型调整
        if roi_type == 'SUPPORT_PLANE':
            # 支撑面：Z范围缩小到顶部10mm
            roi['z_min'] = roi['z_max'] - 10.0
        elif roi_type == 'FRONT_EDGE':
            # 前边缘：Y范围缩小到前部50mm
            roi['y_max'] = roi['y_min'] + 50.0
        elif roi_type == 'PILLAR':
            # 立柱：X范围缩小到侧边50mm
            roi['x_max'] = roi['x_min'] + 50.0
        
        return api_response(data={
            'roi': roi,
            'message': f'{roi_type} ROI自动填充完成'
        })
    
    except Exception as e:
        logger.exception("自动填充ROI失败")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def preview_crop(request):
    """预览ROI裁剪结果"""
    try:
        data = json.loads(request.body)
        
        roi = data.get('roi')
        pointcloud = data.get('pointcloud')
        
        if not roi or not pointcloud:
            return api_response(error='缺少ROI或点云数据', status=400)
        
        import numpy as np
        
        # 获取点云数据
        points = np.array(pointcloud.get('points', []))
        
        if len(points) == 0:
            return api_response(error='点云为空', status=400)
        
        # 裁剪点云
        mask = (
            (points[:, 0] >= roi['x_min']) & (points[:, 0] <= roi['x_max']) &
            (points[:, 1] >= roi['y_min']) & (points[:, 1] <= roi['y_max']) &
            (points[:, 2] >= roi['z_min']) & (points[:, 2] <= roi['z_max'])
        )
        
        cropped_points = points[mask]
        
        # 统计信息
        total_points = len(points)
        valid_points = len(cropped_points)
        point_ratio = valid_points / total_points if total_points > 0 else 0
        
        # 简化分析（按Z高度分层）
        if valid_points > 0:
            z_values = cropped_points[:, 2]
            z_median = np.median(z_values)
            
            # 支撑面点（顶部10mm）
            support_points = np.sum(z_values > (z_median + 40))
            
            # 边缘点（前部区域）
            edge_points = np.sum(cropped_points[:, 1] < (roi['y_min'] + 50))
            
            # 立柱点（侧边区域）
            pillar_points = np.sum(cropped_points[:, 0] < (roi['x_min'] + 50))
        else:
            support_points = 0
            edge_points = 0
            pillar_points = 0
        
        result = {
            'valid_points': int(valid_points),
            'support_points': int(support_points),
            'edge_points': int(edge_points),
            'pillar_points': int(pillar_points),
            'point_ratio': float(point_ratio),
            'cropped_pointcloud': {
                'points': cropped_points.tolist()
            }
        }
        
        return api_response(data=result)
    
    except Exception as e:
        logger.exception("预览裁剪失败")
        return api_response(error=str(e), status=500)
