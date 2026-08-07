"""3D 料架离线数据包 REST API。"""

import json

import numpy as np
from django.http import FileResponse, JsonResponse
from django.views.decorators.http import require_http_methods

from .models import RackLocationRecipe
from .offline_data_service import OfflineDataPackageError, OfflineDataPackageService


def _request_json(request):
    return json.loads(request.body or "{}")


def _error(exc, status=400):
    return JsonResponse({"success": False, "error": str(exc)}, status=status)


@require_http_methods(["GET", "POST"])
def packages(request):
    service = OfflineDataPackageService()
    if request.method == "GET":
        # 添加 include_raw 参数支持
        include_raw = request.GET.get('include_raw', 'true').lower() == 'true'
        return JsonResponse({"success": True, "packages": service.list_packages(include_raw=include_raw)})
    try:
        data = _request_json(request)
        if data.get("manual_save") is not True:
            return _error("数据包只能通过“保存数据包”按钮手动创建", 400)
        recipe = RackLocationRecipe.objects.get(pk=data.get("recipe_id"))
        from apps.vision.rack_location import Rack3DLocator

        cloud = Rack3DLocator()._load_pointcloud(data.get("pointcloud_token"))
        hand_eye = _hand_eye_matrix(recipe)
        robot_pose = _robot_pose_matrix(recipe)
        created = service.create_package(
            pointcloud=cloud,
            hand_eye_matrix=hand_eye,
            robot_pose_matrix=robot_pose,
            roi_config={
                **(recipe.roi_config or {}),
                **(data.get("roi_config") or {}),
            },
            recipe=recipe,
            layer_no=int(data.get("layer_no") or recipe.layer_no),
            camera_info={
                "source": data.get("source") or "workbench",
                "width": int(cloud.shape[1]) if cloud.ndim == 3 else int(cloud.shape[0]),
                "height": int(cloud.shape[0]) if cloud.ndim == 3 else 1,
                "frame_index": data.get("frame_index"),
            },
            result=data.get("result"),
            description=data.get("description") or "",
        )
        return JsonResponse({"success": True, "package": created}, status=201)
    except RackLocationRecipe.DoesNotExist:
        return _error("配方不存在", 404)
    except (ValueError, OfflineDataPackageError, json.JSONDecodeError) as exc:
        return _error(exc)


@require_http_methods(["GET"])
def package_detail(request, package_name):
    """获取数据包详情"""
    try:
        service = OfflineDataPackageService()
        detail = service.package_detail(package_name)
        return JsonResponse({"success": True, "package": detail})
    except OfflineDataPackageError as exc:
        return _error(exc, 404)
    except Exception as exc:
        # 捕获其他异常并提供友好的错误信息
        import traceback
        error_msg = f"获取数据包详情失败: {str(exc)}"
        print(f"Error in package_detail: {traceback.format_exc()}")
        return _error(error_msg, 500)


@require_http_methods(["POST"])
def load_package(request, package_name):
    """加载数据包到工作台"""
    try:
        service = OfflineDataPackageService()
        data = _request_json(request)
        recipe_id = data.get("recipe_id")
        
        # 检查是否为原始数据包
        package_dir = service.base_dir / package_name
        is_raw = service._is_raw_package(package_dir) and not (package_dir / "metadata.json").is_file()
        
        if is_raw:
            # 加载原始数据包
            payload = service.create_workbench_copy_from_raw(package_name, recipe_id=recipe_id)
        else:
            # 加载标准数据包
            payload = service.create_workbench_copy(package_name, recipe_id=recipe_id)
        
        return JsonResponse({"success": True, "package": payload})
    except OfflineDataPackageError as exc:
        return _error(exc, 404)
    except Exception as exc:
        import traceback
        error_msg = f"加载数据包失败: {str(exc)}"
        print(f"Error in load_package: {traceback.format_exc()}")
        return _error(error_msg, 500)


@require_http_methods(["POST"])
def reprocess_package(request, package_name):
    """重新处理数据包"""
    try:
        data = _request_json(request)
        service = OfflineDataPackageService()
        
        # 检查是否为原始数据包
        package_dir = service.base_dir / package_name
        is_raw = service._is_raw_package(package_dir) and not (package_dir / "metadata.json").is_file()
        
        if is_raw:
            # 原始数据包需要先完成转换才能重新定位
            return _error("原始数据包需要先加载后才能进行定位操作", 400)
        
        result = service.reprocess_package(
            package_name,
            int(data.get("recipe_id")),
            int(data.get("layer_no")),
            data.get("modified_roi"),
        )
        return JsonResponse({"success": True, "result": result})
    except (TypeError, ValueError, OfflineDataPackageError, json.JSONDecodeError) as exc:
        return _error(exc)
    except Exception as exc:
        import traceback
        error_msg = f"重新处理数据包失败: {str(exc)}"
        print(f"Error in reprocess_package: {traceback.format_exc()}")
        return _error(error_msg, 500)


@require_http_methods(["DELETE"])
def delete_package(request, package_name):
    try:
        return JsonResponse({"success": OfflineDataPackageService().delete_package(package_name)})
    except OfflineDataPackageError as exc:
        return _error(exc, 404)


@require_http_methods(["GET"])
def package_preview(request, package_name):
    try:
        service = OfflineDataPackageService()
        
        # 尝试标准预览
        try:
            return FileResponse(service.preview_path(package_name).open("rb"), content_type="image/png")
        except OfflineDataPackageError:
            # 如果标准预览不存在，尝试原始预览
            return FileResponse(service.get_raw_preview(package_name).open("rb"), content_type="image/png")
    except OfflineDataPackageError as exc:
        return _error(exc, 404)


@require_http_methods(["GET"])
def raw_preview(request, package_name):
    """获取原始数据包的预览图（专用端点）"""
    try:
        return FileResponse(
            OfflineDataPackageService().get_raw_preview(package_name).open("rb"),
            content_type="image/png"
        )
    except OfflineDataPackageError as exc:
        return _error(exc, 404)


def _hand_eye_matrix(recipe):
    config = getattr(recipe, "hand_eye_config", {}) or {}
    matrix = config.get("matrix") if isinstance(config, dict) else None
    if isinstance(matrix, list):
        parsed = np.asarray(matrix, dtype=np.float64)
        if parsed.size == 16:
            return parsed.reshape(4, 4)
    calibration = getattr(recipe, "hand_eye_calibration", None)
    calibration_matrix = getattr(calibration, "transformation_matrix", None)
    if calibration_matrix:
        parsed = np.asarray(calibration_matrix, dtype=np.float64)
        if parsed.size == 16:
            return parsed.reshape(4, 4)
    return np.eye(4, dtype=np.float64)


def _robot_pose_matrix(recipe):
    pose = getattr(recipe, "capture_pose", {}) or {}
    matrix = np.eye(4, dtype=np.float64)
    matrix[0, 3] = float(pose.get("X", pose.get("x", 0)) or 0)
    matrix[1, 3] = float(pose.get("Y", pose.get("y", 0)) or 0)
    matrix[2, 3] = float(pose.get("Z", pose.get("z", 0)) or 0)
    return matrix
