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
        return JsonResponse({"success": True, "packages": service.list_packages()})
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
    try:
        return JsonResponse({"success": True, "package": OfflineDataPackageService().package_detail(package_name)})
    except OfflineDataPackageError as exc:
        return _error(exc, 404)


@require_http_methods(["POST"])
def load_package(request, package_name):
    try:
        payload = OfflineDataPackageService().create_workbench_copy(package_name)
        return JsonResponse({"success": True, "package": payload})
    except OfflineDataPackageError as exc:
        return _error(exc, 404)


@require_http_methods(["POST"])
def reprocess_package(request, package_name):
    try:
        data = _request_json(request)
        result = OfflineDataPackageService().reprocess_package(
            package_name,
            int(data.get("recipe_id")),
            int(data.get("layer_no")),
            data.get("modified_roi"),
        )
        return JsonResponse({"success": True, "result": result})
    except (TypeError, ValueError, OfflineDataPackageError, json.JSONDecodeError) as exc:
        return _error(exc)


@require_http_methods(["DELETE"])
def delete_package(request, package_name):
    try:
        return JsonResponse({"success": OfflineDataPackageService().delete_package(package_name)})
    except OfflineDataPackageError as exc:
        return _error(exc, 404)


@require_http_methods(["GET"])
def package_preview(request, package_name):
    try:
        return FileResponse(OfflineDataPackageService().preview_path(package_name).open("rb"), content_type="image/png")
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
