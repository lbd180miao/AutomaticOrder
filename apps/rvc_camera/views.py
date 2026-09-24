"""RVC 相机 REST API 视图（操作独立相机服务进程）。"""
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .client import RvcCameraConfigurationError, RvcCameraError
from .services import RvcCameraService

logger = logging.getLogger(__name__)

service = RvcCameraService()


def api_response(data=None, error=None, status=200):
    if error:
        return JsonResponse({"success": False, "error": error}, status=status)
    return JsonResponse({"success": True, "data": data})


def _json_body(request):
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


@require_http_methods(["GET"])
def demo_page(request):
    cfg = getattr(settings, "AUTOMATIC_ORDER", {}).get("RVC_CAMERA", {})
    return render(request, "rvc_camera_demo.html", {
        "service_url": cfg.get("SERVICE_URL", "http://127.0.0.1:8001"),
        "camera_ip": cfg.get("CAMERA_IP", ""),
        "default_mode": cfg.get("DEFAULT_MODE", "Robust"),
    })


@require_http_methods(["GET"])
def get_status(request):
    try:
        return api_response(data=service.get_status())
    except Exception as exc:  # noqa: BLE001
        logger.exception("获取 RVC 相机状态异常")
        return api_response(error=str(exc), status=500)


@require_http_methods(["GET"])
def find_devices(request):
    try:
        return api_response(data={"devices": service.find_devices()})
    except RvcCameraError as exc:
        return api_response(error=str(exc), status=500)
    except Exception as exc:  # noqa: BLE001
        logger.exception("查找 RVC 设备异常")
        return api_response(error=f"查找设备失败: {exc}", status=500)


@csrf_exempt
@require_http_methods(["POST"])
def connect_camera(request):
    body = _json_body(request)
    try:
        data = service.connect(
            device_sn=body.get("sn"),
            ip=body.get("ip"),
        )
        return api_response(data=data)
    except RvcCameraConfigurationError as exc:
        return api_response(error=str(exc), status=400)
    except RvcCameraError as exc:
        return api_response(error=str(exc), status=500)
    except Exception as exc:  # noqa: BLE001
        logger.exception("连接 RVC 相机异常")
        return api_response(error=f"连接相机失败: {exc}", status=500)


@csrf_exempt
@require_http_methods(["POST"])
def disconnect_camera(request):
    try:
        return api_response(data=service.disconnect())
    except RvcCameraError as exc:
        return api_response(error=str(exc), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def recover_camera(request):
    """释放旧连接、重新初始化 SDK 并重新连接相机。"""
    body = _json_body(request)
    try:
        data = service.recover(sn=body.get("sn"), ip=body.get("ip"))
        return api_response(data=data)
    except RvcCameraError as exc:
        return api_response(error=str(exc), status=500)
    except Exception as exc:  # noqa: BLE001
        logger.exception("恢复 RVC 相机连接异常")
        return api_response(error=f"恢复连接失败: {exc}", status=500)


@csrf_exempt
@require_http_methods(["POST"])
def set_mode(request):
    body = _json_body(request)
    mode = body.get("mode") or request.GET.get("mode")
    if not mode:
        return api_response(error="缺少 mode 参数", status=400)
    try:
        return api_response(data=service.set_mode(mode))
    except RvcCameraConfigurationError as exc:
        return api_response(error=str(exc), status=400)
    except RvcCameraError as exc:
        return api_response(error=str(exc), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def set_exposure(request):
    body = _json_body(request)
    try:
        data = service.set_exposure(
            exposure_2d=body.get("exposure_2d"),
            exposure_3d=body.get("exposure_3d"),
            projector_brightness=body.get("projector_brightness"),
        )
        return api_response(data=data)
    except (RvcCameraError, RvcCameraConfigurationError) as exc:
        return api_response(error=str(exc), status=400 if isinstance(exc, RvcCameraConfigurationError) else 500)


@csrf_exempt
@require_http_methods(["POST"])
def capture_frame(request):
    """触发一次采集，返回点云/2D 图的路径与元数据。"""
    body = _json_body(request)
    frame_type = (body.get("frame_type") or "POINTCLOUD").upper()
    mode = body.get("mode")
    try:
        data = service.capture_frame_data(frame_type=frame_type, mode=mode)
        # numpy 数组不能直接 JSON 序列化，移除后只返回元数据
        data.pop("data", None)
        return api_response(data=data)
    except RvcCameraConfigurationError as exc:
        return api_response(error=str(exc), status=400)
    except RvcCameraError as exc:
        return api_response(error=str(exc), status=500)
    except Exception as exc:  # noqa: BLE001
        logger.exception("RVC 采集异常")
        return api_response(error=f"采集失败: {exc}", status=500)
