"""Compatibility API using the shared point-cloud template matcher."""
from typing import Any, Dict
import numpy as np
from django.conf import settings
from .providers import ProviderFactory
from .processors import PointCloudProcessor

class RackPositioningService:
    def __init__(self, mode=None, **kwargs):
        self.mode = (mode or getattr(settings, 'RACK_3D_POSITIONING_MODE', 'REAL')).upper()
        self.depth_camera_provider = ProviderFactory.create_depth_camera_provider(self.mode, **kwargs)
        self.hand_eye_provider = ProviderFactory.create_hand_eye_provider(self.mode, **kwargs)
        self.robot_pose_provider = ProviderFactory.create_robot_pose_provider(self.mode, **kwargs)
        self.processor = PointCloudProcessor()

    def execute_positioning(self, recipe_id, layer_no, save=True):
        from ..models import RackLocationRecipe
        from ..rack_cloud_service import evaluate_cloud
        recipe = RackLocationRecipe.objects.get(pk=recipe_id, enabled=True)
        frame = self.depth_camera_provider.capture_pointcloud(recipe_id=recipe_id, layer_no=layer_no)
        metadata = dict(frame.get('metadata') or {})
        metadata.setdefault('source', frame.get('source', 'unknown'))
        metadata.setdefault('camera', {})
        metadata['camera'].setdefault('pointcloud_unit', 'mm')
        return evaluate_cloud(recipe, frame['data'], metadata, layer_no=layer_no, save_record=save)

    def capture_and_transform(
        self,
        recipe_id: int,
        layer_no: int,
        max_preview_points: int = 4000,
    ) -> Dict[str, Any]:
        """采集点云并转换到机器人基坐标系，返回预览用（降采样）点集与边界。

        供前端「采集点云」按钮渲染 Canvas；不做定位计算、不落库。
        """
        pc = self.depth_camera_provider.capture_pointcloud(recipe_id=recipe_id, layer_no=layer_no)
        T_fc = self.hand_eye_provider.get_hand_eye_matrix(recipe_id)
        T_bf = self.robot_pose_provider.get_robot_pose_matrix(layer_no, recipe_id)
        robot_cloud = self.processor.transform_to_robot_coords(pc['data'], T_fc, T_bf)

        preview = robot_cloud
        if preview.shape[0] > max_preview_points:
            step = int(np.ceil(preview.shape[0] / max_preview_points))
            preview = preview[::step]

        bounds = {}
        if robot_cloud.shape[0]:
            bounds = {
                'x_min': float(robot_cloud[:, 0].min()), 'x_max': float(robot_cloud[:, 0].max()),
                'y_min': float(robot_cloud[:, 1].min()), 'y_max': float(robot_cloud[:, 1].max()),
                'z_min': float(robot_cloud[:, 2].min()), 'z_max': float(robot_cloud[:, 2].max()),
            }
        return {
            'mode': self.mode,
            'frame_index': pc.get('frame_index'),
            'point_count': int(robot_cloud.shape[0]),
            'preview_points': preview.round(2).tolist(),
            'bounds': bounds,
        }
