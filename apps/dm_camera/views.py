"""
DM相机REST API视图
"""
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
import json

from .models import DMCameraConfig, DMCaptureRecord, DMCameraSession
from .services import DMCameraService
from .sdk_wrapper import DMCameraException

logger = logging.getLogger(__name__)

# 初始化服务
dm_service = DMCameraService()


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
def find_devices(request):
    """查找所有可用的DM相机设备"""
    try:
        devices = dm_service.find_devices()
        return api_response(data={'devices': devices})
    except DMCameraException as e:
        logger.error(f"查找设备失败: {str(e)}")
        return api_response(error=str(e), status=500)
    except Exception as e:
        logger.exception("查找设备异常")
        return api_response(error="查找设备失败", status=500)


@csrf_exempt
@require_http_methods(["POST"])
def connect_camera(request):
    """连接到DM相机"""
    try:
        data = json.loads(request.body) if request.body else {}
        device_sn = data.get('device_sn')
        config_id = data.get('config_id')
        
        result = dm_service.connect(device_sn=device_sn, config_id=config_id)
        return api_response(data=result)
    
    except DMCameraException as e:
        logger.error(f"连接设备失败: {str(e)}")
        return api_response(error=str(e), status=500)
    except Exception as e:
        logger.exception("连接设备异常")
        return api_response(error="连接设备失败", status=500)


@csrf_exempt
@require_http_methods(["POST"])
def disconnect_camera(request):
    """断开相机连接"""
    try:
        dm_service.disconnect()
        return api_response(data={'message': '设备已断开连接'})
    
    except DMCameraException as e:
        logger.error(f"断开设备失败: {str(e)}")
        return api_response(error=str(e), status=500)
    except Exception as e:
        logger.exception("断开设备异常")
        return api_response(error="断开设备失败", status=500)


@csrf_exempt
@require_http_methods(["POST"])
def start_stream(request):
    """开启数据流"""
    try:
        result = dm_service.start_stream()
        return api_response(data=result)
    
    except DMCameraException as e:
        logger.error(f"开启数据流失败: {str(e)}")
        return api_response(error=str(e), status=500)
    except Exception as e:
        logger.exception("开启数据流异常")
        return api_response(error="开启数据流失败", status=500)


@csrf_exempt
@require_http_methods(["POST"])
def stop_stream(request):
    """停止数据流"""
    try:
        result = dm_service.stop_stream()
        return api_response(data=result)
    
    except DMCameraException as e:
        logger.error(f"停止数据流失败: {str(e)}")
        return api_response(error=str(e), status=500)
    except Exception as e:
        logger.exception("停止数据流异常")
        return api_response(error="停止数据流失败", status=500)


@csrf_exempt
@require_http_methods(["POST"])
def capture_frame(request):
    """捕获一帧数据"""
    try:
        data = json.loads(request.body) if request.body else {}
        frame_type = data.get('frame_type', 'DEPTH')
        save_record = data.get('save_record', True)
        
        result = dm_service.capture(frame_type=frame_type, save_record=save_record)
        return api_response(data=result)
    
    except DMCameraException as e:
        logger.error(f"捕获帧失败: {str(e)}")
        return api_response(error=str(e), status=500)
    except Exception as e:
        logger.exception("捕获帧异常")
        return api_response(error="捕获帧失败", status=500)


@require_http_methods(["GET"])
def get_status(request):
    """获取当前状态"""
    try:
        status = dm_service.get_status()
        return api_response(data=status)
    
    except Exception as e:
        logger.exception("获取状态异常")
        return api_response(error="获取状态失败", status=500)


# ========== 配置管理 ==========

@require_http_methods(["GET"])
def list_configs(request):
    """获取配置列表"""
    try:
        configs = DMCameraConfig.objects.all()
        
        result = [{
            'id': config.id,
            'name': config.name,
            'device_sn': config.device_sn,
            'frame_rate': config.frame_rate,
            'exposure_time': config.exposure_time,
            'trigger_mode': config.trigger_mode,
            'is_active': config.is_active,
            'created_at': config.created_at.isoformat(),
            'updated_at': config.updated_at.isoformat(),
        } for config in configs]
        
        return api_response(data={'configs': result})
    
    except Exception as e:
        logger.exception("获取配置列表异常")
        return api_response(error="获取配置列表失败", status=500)


@require_http_methods(["GET"])
def get_config(request, config_id):
    """获取配置详情"""
    try:
        config = get_object_or_404(DMCameraConfig, id=config_id)
        
        result = {
            'id': config.id,
            'name': config.name,
            'device_sn': config.device_sn,
            'frame_rate': config.frame_rate,
            'exposure_time': config.exposure_time,
            'trigger_mode': config.trigger_mode,
            'confidence_filter_enable': config.confidence_filter_enable,
            'confidence_threshold': config.confidence_threshold,
            'flying_pixels_filter_enable': config.flying_pixels_filter_enable,
            'flying_pixels_threshold': config.flying_pixels_threshold,
            'spatial_filter_enable': config.spatial_filter_enable,
            'spatial_threshold': config.spatial_threshold,
            'is_active': config.is_active,
            'created_at': config.created_at.isoformat(),
            'updated_at': config.updated_at.isoformat(),
        }
        
        return api_response(data=result)
    
    except Exception as e:
        logger.exception("获取配置详情异常")
        return api_response(error="获取配置详情失败", status=500)


@csrf_exempt
@require_http_methods(["POST"])
def create_config(request):
    """创建配置"""
    try:
        data = json.loads(request.body)
        
        # 如果设置为激活，则取消其他配置的激活状态
        if data.get('is_active'):
            DMCameraConfig.objects.filter(is_active=True).update(is_active=False)
        
        config = DMCameraConfig.objects.create(
            name=data['name'],
            device_sn=data.get('device_sn', ''),
            frame_rate=data.get('frame_rate', 10),
            exposure_time=data.get('exposure_time', 1000),
            trigger_mode=data.get('trigger_mode', 'ACTIVE'),
            confidence_filter_enable=data.get('confidence_filter_enable', True),
            confidence_threshold=data.get('confidence_threshold', 15),
            flying_pixels_filter_enable=data.get('flying_pixels_filter_enable', True),
            flying_pixels_threshold=data.get('flying_pixels_threshold', 5),
            spatial_filter_enable=data.get('spatial_filter_enable', True),
            spatial_threshold=data.get('spatial_threshold', 5),
            is_active=data.get('is_active', False),
        )
        
        return api_response(data={'id': config.id, 'message': '配置创建成功'})
    
    except Exception as e:
        logger.exception("创建配置异常")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
def update_config(request, config_id):
    """更新配置"""
    try:
        config = get_object_or_404(DMCameraConfig, id=config_id)
        data = json.loads(request.body)
        
        # 如果设置为激活，则取消其他配置的激活状态
        if data.get('is_active'):
            DMCameraConfig.objects.exclude(id=config_id).update(is_active=False)
        
        # 更新字段
        for field in ['name', 'device_sn', 'frame_rate', 'exposure_time', 'trigger_mode',
                     'confidence_filter_enable', 'confidence_threshold',
                     'flying_pixels_filter_enable', 'flying_pixels_threshold',
                     'spatial_filter_enable', 'spatial_threshold', 'is_active']:
            if field in data:
                setattr(config, field, data[field])
        
        config.save()
        
        return api_response(data={'message': '配置更新成功'})
    
    except Exception as e:
        logger.exception("更新配置异常")
        return api_response(error=str(e), status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_config(request, config_id):
    """删除配置"""
    try:
        config = get_object_or_404(DMCameraConfig, id=config_id)
        config.delete()
        
        return api_response(data={'message': '配置删除成功'})
    
    except Exception as e:
        logger.exception("删除配置异常")
        return api_response(error=str(e), status=500)


# ========== 采集记录 ==========

@require_http_methods(["GET"])
def list_captures(request):
    """获取采集记录列表"""
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        frame_type = request.GET.get('frame_type')
        
        queryset = DMCaptureRecord.objects.all()
        
        if frame_type:
            queryset = queryset.filter(frame_type=frame_type)
        
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        
        records = [{
            'id': record.id,
            'frame_type': record.frame_type,
            'frame_index': record.frame_index,
            'width': record.width,
            'height': record.height,
            'temperature_chip': record.temperature_chip,
            'preview_url': record.preview_image.url if record.preview_image else None,
            'captured_at': record.captured_at.isoformat(),
            'config_name': record.config.name if record.config else None,
        } for record in page_obj]
        
        return api_response(data={
            'records': records,
            'total': paginator.count,
            'page': page,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
        })
    
    except Exception as e:
        logger.exception("获取采集记录异常")
        return api_response(error="获取采集记录失败", status=500)


@require_http_methods(["GET"])
def get_capture(request, capture_id):
    """获取采集记录详情"""
    try:
        record = get_object_or_404(DMCaptureRecord, id=capture_id)
        
        result = {
            'id': record.id,
            'frame_type': record.frame_type,
            'frame_index': record.frame_index,
            'width': record.width,
            'height': record.height,
            'temperature_chip': record.temperature_chip,
            'temperature_laser1': record.temperature_laser1,
            'temperature_laser2': record.temperature_laser2,
            'preview_url': record.preview_image.url if record.preview_image else None,
            'data_file_url': record.data_file.url if record.data_file else None,
            'metadata': record.metadata,
            'captured_at': record.captured_at.isoformat(),
            'config': {
                'id': record.config.id,
                'name': record.config.name
            } if record.config else None,
        }
        
        return api_response(data=result)
    
    except Exception as e:
        logger.exception("获取采集记录详情异常")
        return api_response(error="获取采集记录详情失败", status=500)


# ========== 演示页面 ==========

@require_http_methods(["GET"])
def demo_page(request):
    """演示页面"""
    return render(request, 'dm_camera_demo.html')
