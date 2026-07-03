"""3D 料架定位离线数据包的文件存储服务。"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from django.conf import settings
from django.urls import reverse
from django.utils import timezone


class OfflineDataPackageError(ValueError):
    """数据包不存在、损坏或格式不合法。"""


class OfflineDataPackageService:
    """保存、加载、列出、重新定位和删除离线数据包。"""

    REQUIRED_FILES = (
        "metadata.json",
        "pointcloud.npy",
        "hand_eye_matrix.npy",
        "robot_pose_matrix.npy",
        "roi_config.json",
    )
    PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

    def __init__(self, base_dir: Optional[str] = None):
        configured = getattr(settings, "OFFLINE_DATA_PACKAGE_DIR", None)
        self.base_dir = Path(base_dir or configured or (Path(settings.BASE_DIR) / "docs" / "pic"))
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.base_dir / "index.json"

    def create_package(
        self,
        pointcloud: np.ndarray,
        hand_eye_matrix: np.ndarray,
        robot_pose_matrix: np.ndarray,
        roi_config: Dict[str, Any],
        recipe,
        layer_no: int,
        camera_info: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        description: str = "",
    ) -> Dict[str, Any]:
        cloud = self._validate_pointcloud(pointcloud)
        hand_eye = self._validate_matrix(hand_eye_matrix, "手眼标定矩阵")
        robot_pose = self._validate_matrix(robot_pose_matrix, "机器人位姿矩阵")
        created_at = timezone.now()
        package_name = self._unique_package_name(recipe.position_no, layer_no, created_at)
        package_dir = self.base_dir / package_name
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{package_name}-", dir=self.base_dir))

        metadata = {
            "package_name": package_name,
            "created_at": created_at.isoformat(),
            "source": camera_info.get("source", "workbench"),
            "description": str(description or ""),
            "recipe": self._recipe_metadata(recipe),
            "layer": {"layer_no": int(layer_no)},
            "camera": {
                **self._json_safe(camera_info),
                "width": int(camera_info.get("width") or self._cloud_width(cloud)),
                "height": int(camera_info.get("height") or self._cloud_height(cloud)),
            },
            "robot": self._json_safe(getattr(recipe, "capture_pose", {}) or {}),
            "point_count": int(cloud.reshape(-1, 3).shape[0]),
            "has_result": bool(result),
        }

        try:
            self._write_json(temp_dir / "metadata.json", metadata)
            self._write_json(temp_dir / "roi_config.json", roi_config or {})
            np.save(temp_dir / "pointcloud.npy", cloud, allow_pickle=False)
            np.save(temp_dir / "hand_eye_matrix.npy", hand_eye, allow_pickle=False)
            np.save(temp_dir / "robot_pose_matrix.npy", robot_pose, allow_pickle=False)
            if result:
                self._write_json(temp_dir / "result.json", result)
            self._write_preview(temp_dir / "preview.png", cloud)
            os.replace(temp_dir, package_dir)
            self._rebuild_index()
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        return {**self._summary(metadata), "package_path": str(package_dir)}

    def load_package(self, package_name: str) -> Dict[str, Any]:
        package_dir = self._package_dir(package_name)
        missing = [name for name in self.REQUIRED_FILES if not (package_dir / name).is_file()]
        if missing:
            raise OfflineDataPackageError(f"数据包文件缺失: {', '.join(missing)}")
        try:
            metadata = self._read_json(package_dir / "metadata.json")
            roi_config = self._read_json(package_dir / "roi_config.json")
            pointcloud = self._validate_pointcloud(np.load(package_dir / "pointcloud.npy", allow_pickle=False))
            hand_eye = self._validate_matrix(
                np.load(package_dir / "hand_eye_matrix.npy", allow_pickle=False), "手眼标定矩阵"
            )
            robot_pose = self._validate_matrix(
                np.load(package_dir / "robot_pose_matrix.npy", allow_pickle=False), "机器人位姿矩阵"
            )
            result_path = package_dir / "result.json"
            result = self._read_json(result_path) if result_path.is_file() else None
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise OfflineDataPackageError(f"数据包损坏: {package_name}") from exc
        return {
            "metadata": metadata,
            "roi_config": roi_config,
            "pointcloud": pointcloud,
            "hand_eye_matrix": hand_eye,
            "robot_pose_matrix": robot_pose,
            "result": result,
            "package_path": str(package_dir),
        }

    def package_detail(self, package_name: str) -> Dict[str, Any]:
        package = self.load_package(package_name)
        metadata = package["metadata"]
        return {
            **self._summary(metadata),
            "metadata": metadata,
            "roi_config": package["roi_config"],
            "result": package["result"],
            "pointcloud_shape": list(package["pointcloud"].shape),
        }

    def list_packages(self, limit: int = 100) -> List[Dict[str, Any]]:
        summaries: List[Dict[str, Any]] = []
        for child in self.base_dir.iterdir():
            if not child.is_dir() or child.name.startswith("."):
                continue
            try:
                metadata = self._read_json(child / "metadata.json")
                summaries.append(self._summary(metadata))
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                continue
        summaries.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return summaries[: max(0, int(limit))]

    def create_workbench_copy(self, package_name: str) -> Dict[str, Any]:
        package = self.load_package(package_name)
        from apps.vision.rack_location import RackLocationService

        token, preview_url, width, height = RackLocationService()._persist_workbench_frame(
            package["pointcloud"]
        )
        return {
            "pointcloud_token": token,
            "preview_image_url": preview_url,
            "image_width": width,
            "image_height": height,
            "source": f"offline_package:{package_name}",
            "roi_config": package["roi_config"],
            "result": package["result"],
            "metadata": package["metadata"],
        }

    def reprocess_package(
        self,
        package_name: str,
        recipe_id: int,
        layer_no: int,
        modified_roi: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        package = self.load_package(package_name)
        roi = modified_roi or package["roi_config"]
        if any(key in roi for key in ("support", "edge", "pillar")):
            roi = roi.get("support") or roi.get("edge") or roi.get("pillar") or {}
        workbench = self.create_workbench_copy(package_name)
        from apps.vision.rack_location import Rack3DLocator

        result = Rack3DLocator().test_locate(
            token=workbench["pointcloud_token"],
            roi_3d=roi,
            recipe_id=recipe_id,
            rack_side=(package["metadata"].get("recipe") or {}).get("rack_side") or "LEFT",
            layer_no=int(layer_no),
        )
        package_dir = self._package_dir(package_name)
        self._write_json(package_dir / "result.json", result)
        metadata = package["metadata"]
        metadata["has_result"] = True
        metadata["last_reprocessed_at"] = timezone.now().isoformat()
        self._write_json(package_dir / "metadata.json", metadata)
        self._rebuild_index()
        return result

    def delete_package(self, package_name: str) -> bool:
        package_dir = self._package_dir(package_name)
        shutil.rmtree(package_dir)
        self._rebuild_index()
        return True

    def preview_path(self, package_name: str) -> Path:
        preview = self._package_dir(package_name) / "preview.png"
        if not preview.is_file():
            raise OfflineDataPackageError("数据包预览图不存在")
        return preview

    def _package_dir(self, package_name: str) -> Path:
        if not package_name or not self.PACKAGE_NAME_RE.fullmatch(str(package_name)):
            raise OfflineDataPackageError("数据包名称不合法")
        package_dir = (self.base_dir / package_name).resolve()
        if package_dir.parent != self.base_dir.resolve() or not package_dir.is_dir():
            raise OfflineDataPackageError(f"数据包不存在: {package_name}")
        return package_dir

    def _summary(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        recipe = metadata.get("recipe") or {}
        layer = metadata.get("layer") or {}
        package_name = metadata["package_name"]
        return {
            "package_name": package_name,
            "created_at": metadata.get("created_at", ""),
            "recipe_name": recipe.get("recipe_name", "未关联配方"),
            "recipe_id": recipe.get("recipe_id"),
            "position_no": recipe.get("position_no"),
            "layer_no": layer.get("layer_no"),
            "source": metadata.get("source", ""),
            "point_count": metadata.get("point_count", 0),
            "has_result": bool(metadata.get("has_result")),
            "preview_url": reverse("vision:offline_package_preview", args=[package_name]),
        }

    def _rebuild_index(self) -> None:
        payload = {"updated_at": timezone.now().isoformat(), "packages": self.list_packages(100000)}
        temp_path = self.index_path.with_suffix(".json.tmp")
        self._write_json(temp_path, payload)
        os.replace(temp_path, self.index_path)

    def _unique_package_name(self, position_no: int, layer_no: int, created_at: datetime) -> str:
        stem = created_at.strftime(f"%Y-%m-%d_POS{int(position_no)}_L{int(layer_no)}_%H%M%S")
        candidate = stem
        counter = 1
        while (self.base_dir / candidate).exists():
            counter += 1
            candidate = f"{stem}_{counter}"
        return candidate

    @staticmethod
    def _validate_pointcloud(value: np.ndarray) -> np.ndarray:
        cloud = np.asarray(value)
        valid = (cloud.ndim == 3 and cloud.shape[2] == 3) or (cloud.ndim == 2 and cloud.shape[1] == 3)
        if not valid or cloud.size == 0:
            raise OfflineDataPackageError(f"点云格式错误: {cloud.shape}")
        return cloud

    @staticmethod
    def _validate_matrix(value: np.ndarray, label: str) -> np.ndarray:
        matrix = np.asarray(value, dtype=np.float64)
        if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
            raise OfflineDataPackageError(f"{label}必须为有效的 4x4 矩阵")
        return matrix

    @staticmethod
    def _recipe_metadata(recipe) -> Dict[str, Any]:
        fields = (
            "recipe_name", "position_no", "rack_side", "standard_x", "standard_y", "standard_z",
            "max_offset_x", "max_offset_y", "max_offset_z", "confidence_threshold",
        )
        data = {"recipe_id": getattr(recipe, "id", None)}
        data.update({field: getattr(recipe, field, None) for field in fields})
        return OfflineDataPackageService._json_safe(data)

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): OfflineDataPackageService._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [OfflineDataPackageService._json_safe(item) for item in value]
        if isinstance(value, (Decimal, np.integer, np.floating)):
            return float(value)
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, (datetime, Path)):
            return str(value)
        return value

    @classmethod
    def _write_json(cls, path: Path, payload: Any) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(cls._json_safe(payload), handle, ensure_ascii=False, indent=2)

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _cloud_width(cloud: np.ndarray) -> int:
        return int(cloud.shape[1]) if cloud.ndim == 3 else int(cloud.shape[0])

    @staticmethod
    def _cloud_height(cloud: np.ndarray) -> int:
        return int(cloud.shape[0]) if cloud.ndim == 3 else 1

    @staticmethod
    def _write_preview(path: Path, cloud: np.ndarray) -> None:
        from PIL import Image
        from apps.vision.algorithms import image_io

        preview = image_io.pointcloud_to_preview(cloud)
        Image.fromarray(np.asarray(preview, dtype=np.uint8)).save(path, format="PNG")

