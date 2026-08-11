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
from types import SimpleNamespace
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
        """加载标准数据包（包含所有必需文件）"""
        package_dir = self._package_dir(package_name)
        
        # 检查必需文件，但给出更友好的错误提示
        missing = [name for name in self.REQUIRED_FILES if not (package_dir / name).is_file()]
        if missing:
            # 如果是原始数据包，提供友好的提示
            if self._is_raw_package(package_dir):
                raise OfflineDataPackageError(
                    f"这是一个原始数据包（包含 PointCloud.ply），"
                    f"请使用'加载'功能直接加载，或使用 load_raw_package() 方法加载。"
                )
            else:
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
        """获取数据包详情，支持标准数据包和原始数据包"""
        package_dir = self._package_dir(package_name)
        
        # 检查是否为原始数据包
        is_raw = self._is_raw_package(package_dir) and not (package_dir / "metadata.json").is_file()
        
        if is_raw:
            # 原始数据包，返回简化信息
            package = self.load_raw_package(package_name)
            metadata = package["metadata"]
            return {
                **self._raw_package_summary(package_dir),
                "metadata": metadata,
                "roi_config": package["roi_config"],
                "result": package["result"],
                "pointcloud_shape": list(package["pointcloud"].shape),
                "is_raw": True,
            }
        else:
            # 标准数据包
            package = self.load_package(package_name)
            metadata = package["metadata"]
            return {
                **self._summary(metadata),
                "metadata": metadata,
                "roi_config": package["roi_config"],
                "result": package["result"],
                "pointcloud_shape": list(package["pointcloud"].shape),
                "is_raw": False,
            }

    def list_packages(self, limit: int = 100, include_raw: bool = False) -> List[Dict[str, Any]]:
        summaries: List[Dict[str, Any]] = []
        for child in self.base_dir.iterdir():
            if not child.is_dir() or child.name.startswith("."):
                continue
            try:
                metadata = self._read_json(child / "metadata.json")
                summaries.append(self._summary(metadata))
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                # 如果没有metadata.json，尝试识别为原始数据包（包含PointCloud.ply的文件夹）
                if include_raw and self._is_raw_package(child):
                    summaries.append(self._raw_package_summary(child))
                continue
        summaries.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return summaries[: max(0, int(limit))]

    def create_workbench_copy(self, package_name: str, recipe_id: Optional[Any] = None) -> Dict[str, Any]:
        package = self.load_package(package_name)
        
        cloud = package["pointcloud"]
        if cloud.ndim == 2 and cloud.shape[1] == 3:
            camera_meta = package.get("metadata", {}).get("camera", {})
            w, h = camera_meta.get("width"), camera_meta.get("height")
            if w and h and w * h == cloud.shape[0]:
                cloud = cloud.reshape((int(h), int(w), 3))
        
        from apps.vision.rack_location import RackLocationService

        workbench_service = RackLocationService()
        token, preview_url, width, height = workbench_service._persist_workbench_frame(
            cloud
        )
        payload = {
            "pointcloud_token": token,
            "preview_image_url": preview_url,
            "image_width": width,
            "image_height": height,
            "source": f"offline_package:{package_name}",
            "roi_config": package["roi_config"],
            "result": package["result"],
            "metadata": package["metadata"],
        }

        current_recipe = None
        if recipe_id:
            from apps.vision.models import RackLocationRecipe
            current_recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first()

        projection_config = dict(current_recipe.roi_config or {}) if current_recipe else dict(package["roi_config"] or {})

        try:
            projection_config.setdefault(
                "transform_snapshot",
                (np.array(package["robot_pose_matrix"]) @ np.array(package["hand_eye_matrix"])).tolist(),
            )
            projection_recipe = SimpleNamespace(
                roi_config=projection_config,
                hand_eye_config={},
                capture_pose={},
            )
            payload["recipe_pixel_roi"] = workbench_service.project_recipe_roi_to_pixels(
                cloud, projection_recipe,
            )
        except (TypeError, ValueError, np.linalg.LinAlgError, KeyError) as exc:
            payload["roi_projection_error"] = str(exc)
            # 兜底回退：3D ROI 投影失败时，尝试从数据包 roi_config 中
            # 读取已保存的 2D 像素 target_roi 直接返回给前端，
            # 确保加载数据包后 ROI 框能自动显示在图像上。
            saved_target_roi = (package.get("roi_config") or {}).get("target_roi")
            if saved_target_roi and all(
                saved_target_roi.get(k) is not None for k in ("x", "y", "w", "h")
            ):
                payload["recipe_pixel_roi"] = {
                    **{k: saved_target_roi[k] for k in ("x", "y", "w", "h")},
                    "feature_type": "recipe_3d_roi",
                    "projection_source": "saved_target_roi",
                }
        return payload

    def reprocess_package(
        self,
        package_name: str,
        recipe_id: int,
        layer_no: int,
        modified_roi: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """重新处理数据包，支持标准数据包和原始数据包"""
        package_dir = self._package_dir(package_name)
        
        # 检查是否为原始数据包
        is_raw = self._is_raw_package(package_dir) and not (package_dir / "metadata.json").is_file()
        
        if is_raw:
            # 对于原始数据包，使用 load_raw_package
            package = self.load_raw_package(package_name)
        else:
            # 标准数据包
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
        """删除数据包（支持标准数据包和原始数据包）"""
        package_dir = self._package_dir(package_name)
        
        # 无论是标准数据包还是原始数据包，都可以直接删除文件夹
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

    @staticmethod
    def _is_raw_package(package_dir: Path) -> bool:
        """检查文件夹是否包含原始点云数据（PointCloud.ply 或 PointCloud.npy）"""
        return (package_dir / "PointCloud.ply").is_file() or (package_dir / "pointcloud.npy").is_file()

    def _raw_package_summary(self, package_dir: Path) -> Dict[str, Any]:
        """为原始数据包生成摘要信息"""
        package_name = package_dir.name
        
        # 尝试从文件夹修改时间获取创建时间
        try:
            stat = package_dir.stat()
            created_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
        except Exception:
            created_at = ""
        
        # 尝试获取点云点数
        point_count = 0
        try:
            ply_path = package_dir / "PointCloud.ply"
            npy_path = package_dir / "pointcloud.npy"
            if npy_path.is_file():
                cloud = np.load(npy_path, allow_pickle=False)
                point_count = int(cloud.reshape(-1, 3).shape[0])
            elif ply_path.is_file():
                try:
                    from plyfile import PlyData
                    plydata = PlyData.read(str(ply_path))
                    point_count = len(plydata['vertex'])
                except (ImportError, Exception):
                    pass
        except Exception:
            pass
        
        # 检查是否有预览图
        preview_files = ["Image.png", "preview.png", "image.png"]
        preview_url = None
        for preview_file in preview_files:
            if (package_dir / preview_file).is_file():
                # 为原始数据包生成预览URL
                preview_url = f"/vision/offline/packages/{package_name}/raw-preview/"
                break
        
        return {
            "package_name": package_name,
            "created_at": created_at,
            "recipe_name": f"原始数据-{package_name}",
            "recipe_id": None,
            "position_no": "—",
            "layer_no": "—",
            "source": "raw_folder",
            "point_count": point_count,
            "has_result": False,
            "preview_url": preview_url or "",
            "is_raw": True,  # 标记为原始数据包
        }

    def load_raw_package(self, package_name: str) -> Dict[str, Any]:
        """加载原始数据包（从docs/pic文件夹）"""
        package_dir = self._package_dir(package_name)
        
        # 查找点云文件
        ply_path = package_dir / "PointCloud.ply"
        npy_path = package_dir / "pointcloud.npy"
        
        if ply_path.is_file():
            # 加载PLY点云
            pointcloud = self._load_ply_pointcloud(ply_path)
        elif npy_path.is_file():
            # 加载NPY点云
            pointcloud = np.load(npy_path, allow_pickle=False)
        else:
            raise OfflineDataPackageError(f"数据包中未找到点云文件: {package_name}")

        pointcloud = self._organize_raw_pointcloud(package_name, pointcloud)
        image_height, image_width = pointcloud.shape[:2]
        
        # 使用默认的手眼标定和机器人位姿矩阵
        hand_eye_matrix = np.eye(4, dtype=np.float64)
        robot_pose_matrix = np.eye(4, dtype=np.float64)
        
        # 创建基本的metadata
        metadata = {
            "package_name": package_name,
            "source": "raw_folder",
            "description": f"从原始文件夹导入: {package_name}",
            "recipe": {},
            "layer": {},
            "camera": {
                "width": int(image_width),
                "height": int(image_height),
            },
            "robot": {},
            "point_count": int(pointcloud.reshape(-1, 3).shape[0]),
            "has_result": False,
            "is_raw": True,
        }
        
        return {
            "metadata": metadata,
            "roi_config": {},
            "pointcloud": pointcloud,
            "hand_eye_matrix": hand_eye_matrix,
            "robot_pose_matrix": robot_pose_matrix,
            "result": None,
            "package_path": str(package_dir),
        }

    @staticmethod
    def _load_ply_pointcloud(ply_path: Path) -> np.ndarray:
        """加载PLY格式的点云文件"""
        try:
            from plyfile import PlyData
            
            plydata = PlyData.read(str(ply_path))
            vertex = plydata['vertex']
            
            # 提取XYZ坐标
            x = np.asarray(vertex['x'], dtype=np.float64)
            y = np.asarray(vertex['y'], dtype=np.float64)
            z = np.asarray(vertex['z'], dtype=np.float64)
            
            # 组合成点云数组 (N, 3)
            pointcloud = np.stack([x, y, z], axis=1)
            
            # 必须保留 PLY 的原始行数和像素顺序。无效点会在具体 ROI 裁剪时
            # 过滤；若在这里删除，会破坏 N == width*height，导致无法恢复
            # H×W×3 组织化点云，页面框选坐标也就无法对应到算法点云。
            if not np.isfinite(pointcloud).any():
                raise ValueError("点云中没有有效点")
            
            return pointcloud
            
        except ImportError:
            raise OfflineDataPackageError(
                "需要安装 plyfile 库来加载PLY文件: pip install plyfile"
            )
        except Exception as e:
            raise OfflineDataPackageError(f"加载PLY文件失败: {str(e)}")

    def _organize_raw_pointcloud(self, package_name: str, pointcloud: np.ndarray) -> np.ndarray:
        """按原始预览图尺寸恢复 H×W×3 点云，保证画布像素与点云一一对应。"""
        cloud = np.asarray(pointcloud)
        if cloud.ndim == 3 and cloud.shape[2] == 3:
            return cloud
        if cloud.ndim != 2 or cloud.shape[1] != 3:
            raise OfflineDataPackageError(
                f"原始点云格式错误，应为 H×W×3 或 N×3，实际为 {list(cloud.shape)}"
            )
        try:
            from PIL import Image
            with Image.open(self.get_raw_preview(package_name)) as preview:
                width, height = preview.size
        except Exception as exc:
            raise OfflineDataPackageError(
                f"无法读取原始预览图尺寸，不能恢复组织化点云: {package_name}"
            ) from exc
        expected = int(width) * int(height)
        if cloud.shape[0] != expected:
            raise OfflineDataPackageError(
                f"点云数量与预览图不一致：{cloud.shape[0]} != {width}×{height}，无法进行像素 ROI 计算"
            )
        return cloud.reshape(int(height), int(width), 3)

    def get_raw_preview(self, package_name: str) -> Path:
        """获取原始数据包的预览图路径（不区分大小写）"""
        package_dir = self._package_dir(package_name)
        
        # 查找预览图文件（不区分大小写）
        preview_files = ["Image.png", "preview.png", "image.png", "IMAGE.PNG", "PREVIEW.PNG"]
        
        # 先尝试精确匹配
        for preview_file in preview_files:
            preview_path = package_dir / preview_file
            if preview_path.is_file():
                return preview_path
        
        # 如果精确匹配失败，尝试不区分大小写查找
        try:
            for file in package_dir.iterdir():
                if file.is_file() and file.suffix.lower() == '.png':
                    lower_name = file.name.lower()
                    if 'image' in lower_name or 'preview' in lower_name:
                        return file
        except Exception:
            pass
        
        raise OfflineDataPackageError(f"数据包中未找到预览图: {package_name}")

    def create_workbench_copy_from_raw(self, package_name: str, recipe_id: Optional[Any] = None) -> Dict[str, Any]:
        """从原始数据包创建工作台副本"""
        package = self.load_raw_package(package_name)
        cloud = package["pointcloud"]
        from apps.vision.rack_location import RackLocationService
        token, _generated_preview_url, width, height = (
            RackLocationService()._persist_workbench_frame(cloud)
        )

        metadata = dict(package["metadata"] or {})
        roi_config = dict(package["roi_config"] or {})
        if recipe_id:
            from apps.vision.models import RackLocationRecipe
            recipe = RackLocationRecipe.objects.filter(pk=recipe_id).first()
            if recipe:
                metadata["recipe"] = self._recipe_metadata(recipe)
                metadata["layer"] = {"layer_no": int(recipe.layer_no or 1)}
                roi_config = dict(recipe.roi_config or {})
        metadata["camera"] = {
            **dict(metadata.get("camera") or {}),
            "width": int(width),
            "height": int(height),
        }
        
        # 使用原始预览图
        try:
            preview_path = self.get_raw_preview(package_name)
            # 使用API端点而不是直接media路径
            from django.urls import reverse
            preview_url = reverse('vision:offline_raw_preview', args=[package_name])
        except Exception:
            preview_url = ""
        
        payload = {
            "pointcloud_token": token,
            "preview_image_url": preview_url,
            "image_width": int(width),
            "image_height": int(height),
            "source": f"raw_package:{package_name}",
            "roi_config": roi_config,
            "result": package["result"],
            "metadata": metadata,
        }
        
        return payload
