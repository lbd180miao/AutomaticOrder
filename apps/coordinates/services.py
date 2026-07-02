from copy import deepcopy
from decimal import Decimal

import numpy as np
from django.conf import settings
from django.db import transaction

from apps.vision.coordinate_transform import CoordinateTransformService
from apps.vision.models import RackLocationRecipe


class CoordinateWorkbenchError(Exception):
    def __init__(self, code, message, status=400, fields=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.fields = fields or {}


class CoordinateWorkbenchService:
    HAND_EYE_MATRIX = [
        [1.0, 0.0, 0.0, 30.0],
        [0.0, 1.0, 0.0, -60.0],
        [0.0, 0.0, 1.0, 120.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    POSE_Z = {1: 600.0, 2: 900.0, 3: 1200.0}
    DISPLAY_LIMIT = 1500

    def __init__(self, seed=20260702):
        self.seed = int(seed)
        self.transform_service = CoordinateTransformService()

    def generate_camera_points(self, layer_no):
        layer_no = self._layer(layer_no)
        rng = np.random.default_rng(self.seed + layer_no)
        return np.column_stack([
            rng.uniform(-200.0, 200.0, 3000),
            rng.uniform(-100.0, 100.0, 3000),
            rng.uniform(800.0, 820.0, 3000),
        ]).astype(np.float64)

    def default_draft(self, layer_no):
        layer_no = self._layer(layer_no)
        pose = {
            'x': 1000.0, 'y': 500.0, 'z': self.POSE_Z[layer_no],
            'rx': 0.0, 'ry': 0.0, 'rz': 0.0,
        }
        draft = {
            'recipe_id': None,
            'layer_no': layer_no,
            'mode': str(getattr(settings, 'RACK_3D_POSITIONING_MODE', 'MOCK')).upper(),
            'hand_eye_matrix': deepcopy(self.HAND_EYE_MATRIX),
            'hand_eye_source': 'MOCK 手动矩阵',
            'hand_eye_url': '/vision/hand-eye/',
            'robot_pose': pose,
            'theoretical': {'x': 0.0, 'y': 0.0, 'z': 0.0},
            'roi': {},
        }
        base = self.transform_points(self.generate_camera_points(layer_no), draft)
        lower, upper = base.min(axis=0) - 5.0, base.max(axis=0) + 5.0
        median = np.median(base, axis=0)
        draft['theoretical'] = self._axis_dict(median)
        draft['roi'] = {
            'x_min': float(lower[0]), 'x_max': float(upper[0]),
            'y_min': float(lower[1]), 'y_max': float(upper[1]),
            'z_min': float(lower[2]), 'z_max': float(upper[2]),
        }
        return draft

    def get_config(self, layer_no):
        layer_no = self._layer(layer_no)
        config = self.default_draft(layer_no)
        recipe = self._find_recipe(layer_no)
        if recipe is None:
            return config

        config['recipe_id'] = recipe.id
        if recipe.hand_eye_calibration_id and recipe.hand_eye_calibration.T_flange_camera:
            config['hand_eye_matrix'] = self._matrix(
                recipe.hand_eye_calibration.T_flange_camera
            ).tolist()
            config['hand_eye_source'] = f'手眼标定：{recipe.hand_eye_calibration.name}'
        elif recipe.hand_eye_config:
            try:
                config['hand_eye_matrix'] = self._matrix(recipe.hand_eye_config).tolist()
                config['hand_eye_source'] = '配方手动矩阵'
            except (TypeError, ValueError):
                pass

        if recipe.capture_pose:
            config['robot_pose'].update({
                key: float(recipe.capture_pose.get(key, config['robot_pose'][key]))
                for key in config['robot_pose']
            })
        standards = [float(recipe.standard_x), float(recipe.standard_y), float(recipe.standard_z)]
        if any(abs(value) > 1e-9 for value in standards):
            config['theoretical'] = dict(zip(('x', 'y', 'z'), standards))
        roi = recipe.roi_config or {}
        roi_keys = ('x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max')
        if all(key in roi for key in roi_keys):
            config['roi'] = {key: float(roi[key]) for key in roi_keys}
        return config

    def get_workbench(self, layer_no):
        return self.preview(self.get_config(layer_no))

    def transform_points(self, points, draft):
        hand_eye = self._matrix(draft['hand_eye_matrix'])
        pose = draft['robot_pose']
        base_flange = self.transform_service.pose_to_matrix(
            pose['x'], pose['y'], pose['z'],
            pose['rx'], pose['ry'], pose['rz'],
        )
        return self.transform_service.camera_to_robot_base(
            np.asarray(points, dtype=np.float64), hand_eye, base_flange
        )

    def preview(self, draft):
        config = self._normalise(draft)
        camera = self.generate_camera_points(config['layer_no'])
        base = self.transform_points(camera, config)
        roi = config['roi']
        mask = (
            (base[:, 0] >= roi['x_min']) & (base[:, 0] <= roi['x_max'])
            & (base[:, 1] >= roi['y_min']) & (base[:, 1] <= roi['y_max'])
            & (base[:, 2] >= roi['z_min']) & (base[:, 2] <= roi['z_max'])
        )
        cropped = base[mask]
        if not len(cropped):
            raise CoordinateWorkbenchError('EMPTY_ROI', '当前机器人基坐标 ROI 内没有点', 422)
        actual = self._axis_dict(np.median(cropped, axis=0))
        theoretical = config['theoretical']
        offset = {axis: actual[axis] - theoretical[axis] for axis in ('x', 'y', 'z')}
        hand_eye = self._matrix(config['hand_eye_matrix'])
        pose = config['robot_pose']
        base_flange = self.transform_service.pose_to_matrix(
            pose['x'], pose['y'], pose['z'], pose['rx'], pose['ry'], pose['rz']
        )
        return {
            'config': config,
            'mode': config['mode'],
            'camera_points': self._display(camera),
            'base_points': self._display(base),
            'roi_points': self._display(cropped),
            'point_counts': {'camera': len(camera), 'base': len(base), 'roi': len(cropped)},
            'coordinate_ranges': {
                'camera': self._ranges(camera), 'base': self._ranges(base),
                'roi': self._ranges(cropped),
            },
            'actual': actual,
            'theoretical': theoretical,
            'offset': offset,
            'transforms': {
                'flange_camera': hand_eye.tolist(),
                'base_flange': base_flange.tolist(),
                'base_camera': (base_flange @ hand_eye).tolist(),
            },
        }

    @transaction.atomic
    def save(self, draft):
        config = self._normalise(draft)
        recipe = self._find_recipe(config['layer_no'], config.get('recipe_id'))
        if recipe is None:
            name = f"COORD-L{config['layer_no']}"
            if RackLocationRecipe.objects.filter(recipe_name=name).exists():
                name = f"{name}-MOCK"
            recipe = RackLocationRecipe(
                recipe_name=name, rack_side='BOTH', position_no=1,
                layer_count=3, layer_no=config['layer_no'], enabled=True,
            )

        matrix_payload = {'matrix': config['hand_eye_matrix']}
        if recipe.hand_eye_calibration_id:
            calibration = recipe.hand_eye_calibration
            calibration.T_flange_camera = matrix_payload
            calibration.save(update_fields=['T_flange_camera', 'updated_at'])
        else:
            recipe.hand_eye_config = matrix_payload

        recipe.capture_pose = config['robot_pose']
        recipe.standard_x = Decimal(str(config['theoretical']['x']))
        recipe.standard_y = Decimal(str(config['theoretical']['y']))
        recipe.standard_z = Decimal(str(config['theoretical']['z']))
        recipe.roi_config = {
            **(recipe.roi_config or {}),
            'coordinate_system': 'robot',
            **config['roi'],
        }
        recipe.save()

        if not recipe.hand_eye_calibration_id:
            RackLocationRecipe.objects.filter(
                position_no=1, enabled=True, hand_eye_calibration__isnull=True
            ).exclude(id=recipe.id).update(hand_eye_config=matrix_payload)

        config['recipe_id'] = recipe.id
        config['hand_eye_source'] = (
            f'手眼标定：{recipe.hand_eye_calibration.name}'
            if recipe.hand_eye_calibration_id else '配方手动矩阵'
        )
        return config

    def _normalise(self, draft):
        if not isinstance(draft, dict):
            raise CoordinateWorkbenchError('INVALID_REQUEST', '请求必须是对象')
        layer_no = self._layer(draft.get('layer_no'))
        matrix = self._matrix(draft.get('hand_eye_matrix'))
        pose = self._numbers(draft.get('robot_pose'), ('x', 'y', 'z', 'rx', 'ry', 'rz'))
        theoretical = self._numbers(draft.get('theoretical'), ('x', 'y', 'z'))
        roi = self._numbers(
            draft.get('roi'), ('x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max')
        )
        for axis in ('x', 'y', 'z'):
            if roi[f'{axis}_min'] >= roi[f'{axis}_max']:
                raise CoordinateWorkbenchError(
                    'INVALID_ROI', f'{axis.upper()} Min 必须小于 Max', 400,
                    {f'roi.{axis}_min': '必须小于最大值'},
                )
        return {
            'recipe_id': int(draft['recipe_id']) if draft.get('recipe_id') else None,
            'layer_no': layer_no,
            'mode': str(draft.get('mode') or 'MOCK').upper(),
            'hand_eye_matrix': matrix.tolist(),
            'hand_eye_source': str(draft.get('hand_eye_source') or 'MOCK 手动矩阵'),
            'hand_eye_url': '/vision/hand-eye/',
            'robot_pose': pose,
            'theoretical': theoretical,
            'roi': roi,
        }

    @staticmethod
    def _matrix(value):
        matrix = CoordinateTransformService.parse_matrix_from_json(value)
        if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
            raise CoordinateWorkbenchError('INVALID_MATRIX', '手眼矩阵必须是有限的 4×4 矩阵')
        if not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-8):
            raise CoordinateWorkbenchError('INVALID_MATRIX', '手眼矩阵最后一行必须是 [0,0,0,1]')
        rotation = matrix[:3, :3]
        if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6) or not np.isclose(
            np.linalg.det(rotation), 1.0, atol=1e-6
        ):
            raise CoordinateWorkbenchError('INVALID_MATRIX', '旋转矩阵必须正交且行列式为 +1')
        return matrix.astype(np.float64)

    @staticmethod
    def _numbers(source, keys):
        if not isinstance(source, dict):
            raise CoordinateWorkbenchError('INVALID_REQUEST', '坐标字段必须是对象')
        try:
            result = {key: float(source[key]) for key in keys}
        except (KeyError, TypeError, ValueError) as exc:
            raise CoordinateWorkbenchError('INVALID_REQUEST', f'坐标字段无效: {exc}') from exc
        if not np.isfinite(list(result.values())).all():
            raise CoordinateWorkbenchError('INVALID_REQUEST', '坐标值必须是有限数')
        return result

    @staticmethod
    def _layer(value):
        try:
            layer_no = int(value)
        except (TypeError, ValueError) as exc:
            raise CoordinateWorkbenchError('INVALID_LAYER', '层号必须是 1、2 或 3') from exc
        if layer_no not in (1, 2, 3):
            raise CoordinateWorkbenchError('INVALID_LAYER', '层号必须是 1、2 或 3')
        return layer_no

    @staticmethod
    def _axis_dict(values):
        return {axis: float(value) for axis, value in zip(('x', 'y', 'z'), values)}

    def _find_recipe(self, layer_no, recipe_id=None):
        queryset = RackLocationRecipe.objects.filter(layer_no=layer_no)
        if recipe_id:
            return queryset.filter(id=recipe_id).first()
        return queryset.filter(position_no=1, enabled=True).order_by('-updated_at', '-id').first()

    def _display(self, points):
        if len(points) > self.DISPLAY_LIMIT:
            indices = np.linspace(0, len(points) - 1, self.DISPLAY_LIMIT, dtype=int)
            points = points[indices]
        return np.asarray(points).round(3).tolist()

    @staticmethod
    def _ranges(points):
        lower, upper = np.min(points, axis=0), np.max(points, axis=0)
        return {
            f'{axis}_{edge}': float(value)
            for axis, low, high in zip(('x', 'y', 'z'), lower, upper)
            for edge, value in (('min', low), ('max', high))
        }
