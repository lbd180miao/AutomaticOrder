"""Capture, point-cloud template registration and historical result serialization."""
from __future__ import annotations
from decimal import Decimal
import logging
import json
import os
from typing import Any, Optional
import numpy as np
from django.conf import settings
from django.utils import timezone
from apps.core.constants import AlarmLevel, AlarmSource, RackSide, ResultStatus, SignalDirection, VisionImageType, VisionTaskType
from apps.alarms.services import AlarmService
from apps.devices.services import DeviceService, get_device_adapter
from apps.dm_camera.sdk_wrapper import DMCameraConfigurationError
from apps.rvc_camera.client import RvcCameraConfigurationError
from .algorithms import image_io
from .rack_input import capture_input, cloud_identity
from .models import RackLocationROI3D, RackLocationRecipe, RackLocationResult, VisionImage, VisionTask
from .rack_compensation import compensation_from_result
logger = logging.getLogger(__name__)
LOCATE_TYPE_GLOBAL = 'GLOBAL'
LOCATE_TYPE_LAYER = 'LAYER'


def _decimal(value: Any, places: str = '0.001') -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(places))

def normalize_locate_type(value: Any = None) -> str:
    locate_type = str(value or LOCATE_TYPE_LAYER).strip().upper()
    if locate_type not in {LOCATE_TYPE_GLOBAL, LOCATE_TYPE_LAYER}:
        raise ValueError('locate_type must be GLOBAL or LAYER')
    return locate_type

def normalize_layer_index(value: Any = None, locate_type: Any = None) -> int:
    normalized_type = normalize_locate_type(locate_type)
    if value in (None, ''):
        layer_index = 0 if normalized_type == LOCATE_TYPE_GLOBAL else 1
    else:
        try:
            layer_index = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError('layer_index must be an integer') from exc

    if normalized_type == LOCATE_TYPE_GLOBAL and layer_index != 0:
        raise ValueError('GLOBAL locate_type requires layer_index=0')
    if normalized_type == LOCATE_TYPE_LAYER and layer_index not in {1, 2, 3}:
        raise ValueError('LAYER locate_type requires layer_index 1, 2, or 3')
    return layer_index

def locate_semantics(*, locate_type: Any = None, layer_index: Any = None,
                     layer_no: Any = None, mode: Any = None) -> dict:
    if locate_type is None and mode:
        locate_type = (
            LOCATE_TYPE_GLOBAL
            if str(mode).lower() == RackLocationROI3D.MODE_GLOBAL
            else LOCATE_TYPE_LAYER
        )
    normalized_type = normalize_locate_type(locate_type)
    index_value = layer_index if layer_index not in (None, '') else layer_no
    normalized_index = normalize_layer_index(index_value, normalized_type)
    return {
        'locate_type': normalized_type,
        'layer_index': normalized_index,
        'roi_mode': (
            RackLocationROI3D.MODE_GLOBAL
            if normalized_type == LOCATE_TYPE_GLOBAL
            else RackLocationROI3D.MODE_LOCAL
        ),
        'layer_no': normalized_index,
    }

def roi3d_to_dict(roi: RackLocationROI3D | dict) -> dict:
    if isinstance(roi, dict):
        return {
            'x_min': float(roi['x_min']),
            'x_max': float(roi['x_max']),
            'y_min': float(roi['y_min']),
            'y_max': float(roi['y_max']),
            'z_min': float(roi['z_min']),
            'z_max': float(roi['z_max']),
        }
    return {
        'id': roi.id,
        'recipe_id': roi.recipe_id,
        'roi_name': roi.roi_name,
        'mode': roi.mode,
        'layer_no': roi.layer_no,
        'coordinate_system': roi.coordinate_system,
        'x_min': float(roi.x_min),
        'x_max': float(roi.x_max),
        'y_min': float(roi.y_min),
        'y_max': float(roi.y_max),
        'z_min': float(roi.z_min),
        'z_max': float(roi.z_max),
        'enabled': roi.enabled,
    }

class SampleRackFrameProvider:
    """Explicit preview source, never a fallback for a failed camera."""
    def capture(self, recipe, position_no, layer_no):
        return {'source': 'sample_forced'}


def build_sample_pointcloud(*, side='LEFT', layer_count=3, width=640, height=480, seed=None, **kwargs):
    depth, _, _ = image_io.build_depth_field(side, int(layer_count or 3), width, height, seed=seed)
    return image_io.depth_field_to_pointcloud(depth)


class RVCCameraRackFrameProvider:
    """Frame provider backed by the RVC 3D camera service.

    现役 RVC 相机的 PyRVC 运行在独立进程 ``rvc_service`` 中（Django 只通过
    HTTP 调用）。RvcCameraService.capture_frame_data() 把点云放在 'data' 键，
    PointCloudProcessor.extract_pose() 使用 'organized_pointcloud' 或
    'pointcloud'，此处负责 key 映射（与旧 DM provider 行为一致）。
    """

    def __init__(self, *, fallback_provider: Optional[SampleRackFrameProvider] = None):
        self.fallback_provider = fallback_provider or SampleRackFrameProvider()

    def capture(self, recipe: RackLocationRecipe, position_no: int, layer_no: int) -> dict:
        if getattr(settings, 'VISION_RACK_LOCATION_FORCE_SAMPLE', False):
            frame = self.fallback_provider.capture(recipe, position_no, layer_no)
            frame['source'] = 'sample_forced'
            return frame

        try:
            from apps.rvc_camera.services import RvcCameraService

            service = RvcCameraService()
            if not service.is_connected:
                # 工作台采集不要求事先在相机页面手动连接：相机服务未连接时
                # 自动补连（IP/SN 取自 settings RVC_CAMERA），失败保留原始错误。
                service.ensure_connected()
            # RVC 为单次触发采集，无需 start_stream
            frame = service.capture_frame_data(frame_type='POINTCLOUD', save_record=False)

            # ── key 映射：服务层 'data' -> 算法层 'organized_pointcloud' ──
            result = {
                **frame,
                'source': 'rvc_camera',
                'position_no': position_no,
                'layer_no': layer_no,
            }
            raw_data = frame.get('data')
            if raw_data is not None:
                arr = np.asarray(raw_data)
                width = int(frame.get('width') or frame.get('image_width') or 0)
                height = int(frame.get('height') or frame.get('image_height') or 0)
                if arr.ndim == 3 and arr.shape[2] == 3:
                    # RVC 点云即 H×W×3 组织化点云
                    result['organized_pointcloud'] = arr
                elif arr.ndim == 2 and arr.shape[1] == 3:
                    if width > 0 and height > 0 and arr.shape[0] == width * height:
                        result['organized_pointcloud'] = arr.reshape(height, width, 3)
                    else:
                        result['pointcloud'] = arr
                elif arr.ndim == 1 and width > 0 and height > 0 and arr.size == width * height * 3:
                    result['organized_pointcloud'] = arr.reshape(height, width, 3)
                else:
                    result['pointcloud'] = arr
            return result
        except (DMCameraConfigurationError, RvcCameraConfigurationError):
            # 配置类错误（如不支持的采集模式）不得静默回退模拟数据
            raise
        except Exception:  # Preserve the real SDK/network error and traceback.
            logger.exception('RVC 实时采集失败')
            raise

DMCameraRackFrameProvider = RVCCameraRackFrameProvider

class PlcVisionResultWriter:
    """Write 3D rack-location compensation through the existing device adapter.

    写入前执行二次校验：即使 result.is_success 为 True，也会重新检查
    当前配方的 max_offset 阈值，防止配方修改后过时的 OK 结果被写入。
    """

    def __init__(self, adapter=None, device_service: Optional[DeviceService] = None):
        self.adapter = adapter or get_device_adapter()
        self.device_service = device_service or DeviceService(adapter=self.adapter)

    def _revalidate_offsets(self, result: RackLocationResult) -> str:
        """按当前配方阈值重新校验补偿值，返回空字符串表示通过。"""
        recipe = result.recipe
        if recipe is None:
            return ''  # 无配方时跳过二次校验
        # 只保留置信度检查
        if float(result.confidence) < float(recipe.confidence_threshold):
            return f'置信度不足: {float(result.confidence):.2%} < {float(recipe.confidence_threshold):.2%}'
        return ''

    def _validate_plc_payload(self, payload: dict) -> str:
        if not payload:
            return 'PLC payload 缺失'
        if payload.get('compensation_valid') is not True:
            return '补偿无效，未写入 PLC'
        for key in ('offset_x', 'offset_y', 'offset_z', 'offset_rz'):
            if key not in payload:
                return f'PLC payload 缺少 {key}'
            try:
                float(payload[key])
            except (TypeError, ValueError):
                return f'PLC payload {key} 不是有效数值'
        return ''

    def write(self, result: RackLocationResult) -> dict:
        payload = result.result_data.get('plc_payload') or {}
        if not result.is_success:
            result.plc_write_status = 'SKIPPED'
            result.plc_error_message = '定位NG，未写入有效补偿'
            result.save(update_fields=['plc_write_status', 'plc_error_message', 'updated_at'])
            return {'success': False, 'skipped': True, 'error': result.plc_error_message}

        # New DB contract requires both robot-base groups, validated together.
        from apps.devices.plc_position_debug import dual_group_position
        converted = dual_group_position(
            {**(result.result_data or {}), 'locate_ok': result.is_success}, result.recipe,
        )
        if not converted['is_success']:
            result.plc_write_status = 'REJECTED'
            result.plc_error_message = converted['error_message']
            result.save(update_fields=['plc_write_status', 'plc_error_message', 'updated_at'])
            return {'success': False, 'rejected': True, 'error': result.plc_error_message}
        payload = {**payload, **{key: value for key, value in converted.items()
                                if key.startswith('compensation_')},
                   'compensation_valid': True,
                   **{f'offset_{axis}': converted[f'compensation_{axis}'] for axis in 'xyz'},
                   'offset_rz': result.result_data['robot_groups']['A']['rotation_deg']['rz']}

        # ── 二次校验：按当前配方阈值重新检查 ──
        rejection = self._validate_plc_payload(payload)
        if rejection:
            result.plc_write_status = 'REJECTED'
            result.plc_error_message = rejection
            result.save(update_fields=['plc_write_status', 'plc_error_message', 'updated_at'])
            AlarmService().create(
                source=AlarmSource.VISION,
                level=AlarmLevel.ERROR,
                message=f'VISION_3D PLC写入被拒绝: {rejection}',
                rack=result.rack,
                lock_workstation=True,
            )
            return {'success': False, 'rejected': True, 'error': rejection}

        rejection = self._revalidate_offsets(result)
        if rejection:
            result.plc_write_status = 'REJECTED'
            result.plc_error_message = rejection
            result.save(update_fields=['plc_write_status', 'plc_error_message', 'updated_at'])
            AlarmService().create(
                source=AlarmSource.VISION,
                level=AlarmLevel.ERROR,
                message=f'VISION_3D PLC写入被拒绝(二次校验): {rejection}',
                rack=result.rack,
                lock_workstation=True,
            )
            return {'success': False, 'rejected': True, 'error': rejection}

        response = self.adapter.send_rack_offsets(payload)
        if response.get('success'):
            result.plc_write_status = 'SUCCESS'
            result.plc_error_message = ''
            result.save(update_fields=['plc_write_status', 'plc_error_message', 'updated_at'])
            self.device_service.record_signal(
                device_code='PLC-01',
                signal_name='rack_3d_location_compensation',
                signal_value=f'POS{result.position_no}-L{result.layer_no}',
                direction=SignalDirection.OUT,
                raw_payload=payload,
            )
            return response

        result.plc_write_status = 'FAILED'
        result.plc_error_message = response.get('error', 'PLC写入失败')
        result.save(update_fields=['plc_write_status', 'plc_error_message', 'updated_at'])
        AlarmService().create(
            source=AlarmSource.DEVICE,
            level=AlarmLevel.ERROR,
            message=f'VISION_3D PLC写入失败: {result.plc_error_message}',
            rack=result.rack,
            lock_workstation=True,
        )
        return response

class RackLocationService:
    """All active rack calculations use the saved point-cloud template."""
    def __init__(self, *, frame_provider=None, plc_writer=None):
        self.frame_provider = frame_provider or RVCCameraRackFrameProvider()
        self.plc_writer = plc_writer or PlcVisionResultWriter()
    def _select_recipe(self, *, recipe_id=None, position_no: int = 1,
                       layer_no: int) -> RackLocationRecipe:
        """Select the enabled recipe for the requested workstation and layer."""
        qs = RackLocationRecipe.objects.filter(enabled=True, position_no=position_no)
        if recipe_id:
            return qs.get(pk=recipe_id)
        return qs.get(layer_no=layer_no)

    def _persist_workbench_frame(self, pointcloud, image_2d=None, capture_metadata=None, *, generate_preview=True) -> tuple[str, str, int, int]:
        """把组织化点云持久化为 .npy，并渲染像素一一对应的伪彩预览图。
        
        如果提供了 image_2d，也会保存为 image2d.png。
        generate_preview=False 用于已有预览图的离线包，返回空预览 URL。

        返回 (npy 相对路径 token, 预览图 URL, 宽, 高)。
        """
        cloud = np.asarray(pointcloud, dtype=np.float32)
        if cloud.ndim != 3 or cloud.shape[2] != 3:
            raise ValueError('组织化点云必须是 H x W x 3')
        height, width = int(cloud.shape[0]), int(cloud.shape[1])

        date_dir = timezone.now().strftime('%Y/%m/%d')
        rel_dir = f'vision/rack_workbench/{date_dir}'
        abs_dir = os.path.join(settings.MEDIA_ROOT, rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        stamp = timezone.now().strftime('%H%M%S_%f')
        npy_name = f'rack_workbench_{stamp}.npy'
        np.save(os.path.join(abs_dir, npy_name), cloud)
        with open(os.path.join(abs_dir, npy_name.replace('.npy', '.units.json')), 'w', encoding='utf-8') as marker:
            json.dump({'unit': 'mm', 'capture_metadata': {
                **(capture_metadata or {}), 'source': (capture_metadata or {}).get('source', 'unknown'),
                'captured_at': timezone.now().isoformat(), **cloud_identity(cloud),
            }}, marker)
        npy_rel = f'{rel_dir}/{npy_name}'

        # 保存2D图像（如果有）
        if image_2d is not None:
            try:
                from PIL import Image
                # 确保是PIL Image对象
                if not isinstance(image_2d, Image.Image):
                    # 如果是numpy数组，转换为PIL Image
                    if isinstance(image_2d, np.ndarray):
                        image_2d = Image.fromarray(image_2d)
                
                image_2d_name = npy_name.replace('.npy', '_image2d.png')
                image_2d_path = os.path.join(abs_dir, image_2d_name)
                image_2d.save(image_2d_path, format='PNG')
                logger.info('Saved 2D image: %s', image_2d_path)
            except Exception as exc:
                logger.warning('Failed to save 2D image: %s', exc)

        if not generate_preview:
            return npy_rel, "", width, height

        preview = image_io.pointcloud_to_preview(cloud)
        preview_rel, _, _ = image_io.save_image(
            preview, 'rack_workbench_preview', rel_dir='vision/rack_workbench',
            extension='jpg', jpeg_quality=90,
        )
        preview_url = settings.MEDIA_URL + preview_rel
        return npy_rel, preview_url, width, height

    def _load_workbench_pointcloud(self, token: str):
        """按 token 安全加载持久化点云（限制在 MEDIA_ROOT 内，防目录穿越）。"""
        if not token:
            raise ValueError('点云引用为空，请重新采集')
        media_root = os.path.realpath(settings.MEDIA_ROOT)
        abs_path = os.path.realpath(os.path.join(media_root, token))
        try:
            inside_media = os.path.commonpath([abs_path, media_root]) == media_root
        except ValueError:
            inside_media = False
        if not inside_media:
            raise ValueError('点云路径不在当前数据目录内，请恢复 media 相对路径或重新采集')
        if not os.path.isfile(abs_path):
            logger.error('Point cloud missing: token=%s MEDIA_ROOT=%s', token, media_root)
            raise ValueError(f'点云文件缺失：{token}。请恢复对应 media 文件或重新采集')
        from .pointcloud_units import load_pointcloud_mm
        return load_pointcloud_mm(abs_path)

    @staticmethod
    def _frame_metadata(token, cloud):
        metadata = {'source': 'unknown_legacy_frame'}
        root = os.path.realpath(settings.MEDIA_ROOT)
        path = os.path.realpath(os.path.join(root, str(token or '')))
        if os.path.commonpath([root, path]) != root:
            raise ValueError('点云路径不在当前数据目录内')
        marker = os.path.splitext(path)[0] + '.units.json'
        if os.path.isfile(marker):
            with open(marker, encoding='utf-8') as stream:
                metadata.update(json.load(stream).get('capture_metadata') or {})
        identity = cloud_identity(cloud)
        if metadata.get('pointcloud_sha256') and metadata['pointcloud_sha256'] != identity['pointcloud_sha256']:
            raise ValueError('点云内容与采集记录不一致，请重新加载或采集')
        return {**metadata, **identity}


    def capture_workbench(self, recipe_id=None):
        recipe = RackLocationRecipe.objects.get(pk=recipe_id, enabled=True) if recipe_id else None
        probe = recipe or RackLocationRecipe(recipe_name='WORKBENCH', layer_no=1, layer_count=3)
        frame, cloud = capture_input(self.frame_provider, probe, probe.position_no, probe.layer_no)
        image = frame.get('image_2d')
        if image is None:
            image = frame.get('image')
        metadata = {**(frame.get('metadata') or {}), 'source': frame['source']}
        token, preview, width, height = self._persist_workbench_frame(cloud, image, capture_metadata=metadata)
        raw = frame.get('preview_url', '')
        if image is not None:
            raw = settings.MEDIA_URL + token.replace('.npy', '_image2d.png')
        return {'pointcloud_token': token, 'pointcloud_preview_url': preview,
                'preview_image_url': preview, 'raw_depth_image_url': preview, 'raw_rgb_image_url': raw,
                'image_width': width, 'image_height': height, 'source': frame['source']}

    def capture_standard_image(self, recipe_id=None):
        data = self.capture_workbench(recipe_id)
        return {**data, 'preview_image_url': data['raw_rgb_image_url'] or data['preview_image_url']}

    def project_recipe_roi_to_pixels(self, pointcloud, recipe):
        """Display saved pixel regions; no plane fitting or 3D ROI projection."""
        rois = ((recipe.roi_config or {}).get('cloud_match_config') or {}).get('rois') or []
        if not rois:
            return {}
        x, y = min(r['x'] for r in rois), min(r['y'] for r in rois)
        return {'x': x, 'y': y, 'w': max(r['x']+r['width'] for r in rois)-x,
                'h': max(r['y']+r['height'] for r in rois)-y, 'projection_source': 'cloud_match_config'}

    def calculate_workbench(self, *, token, recipe_id=None, layer_no=1, save_record=False, **kwargs):
        from .rack_cloud_service import evaluate_cloud
        recipe = self._select_recipe(recipe_id=recipe_id, layer_no=layer_no)
        cloud = self._load_workbench_pointcloud(token)
        metadata = self._frame_metadata(token, cloud)
        # Persisted captures are normalized to mm by the frame loader.
        metadata['camera'] = {**metadata.get('camera', {}), 'pointcloud_unit': 'mm'}
        return evaluate_cloud(recipe, cloud, metadata, layer_no=layer_no, token=token, save_record=save_record)

    def trigger(self, *, layer_no, position_no=1, recipe_id=None, rack_side=RackSide.BOTH,
                write_plc=False, product=None, rack=None, workflow=None):
        from .rack_cloud_service import evaluate_cloud
        recipe = self._select_recipe(recipe_id=recipe_id, position_no=position_no, layer_no=layer_no)
        captured = self.capture_workbench(recipe.pk)
        cloud = self._load_workbench_pointcloud(captured['pointcloud_token'])
        metadata = self._frame_metadata(captured['pointcloud_token'], cloud)
        metadata['camera'] = {**metadata.get('camera', {}), 'pointcloud_unit': 'mm'}
        payload = evaluate_cloud(recipe, cloud, metadata, layer_no=layer_no,
                                 token=captured['pointcloud_token'], save_record=True, product=product, rack=rack)
        record = RackLocationResult.objects.get(pk=payload['result_id'])
        if write_plc:
            self.plc_writer.write(record)
        return record


class Rack3DLocator(RackLocationService):
    """Compatibility facade; every calculation delegates to cloud registration."""
    def capture(self, *, recipe_id=None, layer_no=1, **kwargs):
        return self.capture_workbench(recipe_id)

    def _load_pointcloud(self, token):
        return self._load_workbench_pointcloud(token)

    def locate(self, **kwargs):
        return self.trigger(**kwargs)

    def test_locate(self, *, token, recipe_id=None, layer_no=1, **kwargs):
        return self.calculate_workbench(token=token, recipe_id=recipe_id, layer_no=layer_no,
                                        save_record=bool(kwargs.get('save_record', False)))

    def write_result_to_plc(self, result):
        return self.plc_writer.write(result)
    def get_current_recipe(self, *, locate_type, layer_index, rack_type=None):
        semantics = locate_semantics(locate_type=locate_type, layer_index=layer_index)
        qs = RackLocationRecipe.objects.filter(enabled=True, layer_no=semantics['layer_no'])
        if rack_type:
            qs = qs.filter(rack_type=rack_type)
        return qs.order_by('position_no', '-updated_at').first()


def _normalized_plc_payload(result: RackLocationResult, *, locate_type: str,
                            layer_index: int, overall: dict, layer: dict,
                            final: dict) -> dict:
    payload = dict((result.result_data or {}).get('plc_payload') or {})
    rack_compensation = compensation_from_result(
        result.result_data or {},
        fallback_offset={
            'x': float(final.get('x', result.offset_x)),
            'y': float(final.get('y', result.offset_y)),
            'z': float(final.get('z', result.offset_z)),
            'rz': float(final.get('rz', result.offset_rz)),
        },
    )
    final_offset = {
        'x': float(final.get('x', result.offset_x)),
        'y': float(final.get('y', result.offset_y)),
        'z': float(final.get('z', result.offset_z)),
        'rz': float(final.get('rz', result.offset_rz)),
    }
    payload.update({
        'locate_type': payload.get('locate_type', locate_type),
        'layer_index': int(payload.get('layer_index', layer_index)),
        'offset_x': float(payload.get('offset_x', final_offset['x'])),
        'offset_y': float(payload.get('offset_y', final_offset['y'])),
        'offset_z': float(payload.get('offset_z', final_offset['z'])),
        'offset_rz': float(payload.get('offset_rz', final_offset['rz'])),
        'overall_offset': payload.get('overall_offset') or overall or {},
        'layer_offset': payload.get('layer_offset') or layer or {},
        'final_offset': payload.get('final_offset') or final_offset,
        'offset_rx': float(payload.get('offset_rx', rack_compensation['rotation_deg']['rx'])),
        'offset_ry': float(payload.get('offset_ry', rack_compensation['rotation_deg']['ry'])),
        'rack_compensation': payload.get('rack_compensation') or rack_compensation,
        'compensation_matrix': payload.get('compensation_matrix') or rack_compensation['matrix'],
        'robot_taught_place_pose_count': int(payload.get('robot_taught_place_pose_count', 15)),
        'vision_managed_place_pose_count': int(payload.get('vision_managed_place_pose_count', 0)),
        'compensation_valid': bool(payload.get('compensation_valid', result.is_success)),
    })
    return payload

def result_payload(result: RackLocationResult) -> dict:
    result_img = result.vision_task.images.filter(image_type=VisionImageType.RESULT).first()
    depth_img = result.vision_task.images.filter(image_type=VisionImageType.DEPTH).first()
    data = result.result_data or {}
    locate_type = data.get('locate_type') or (
        LOCATE_TYPE_GLOBAL if int(result.layer_no or 0) == 0 else LOCATE_TYPE_LAYER
    )
    layer_index = int(data.get('layer_index', result.layer_no or 0))
    overall = data.get('overall_offset') or {}
    layer = data.get('layer_offset') or {}
    final = data.get('final_offset') or {}
    plc_payload = _normalized_plc_payload(
        result,
        locate_type=locate_type,
        layer_index=layer_index,
        overall=overall,
        layer=layer,
        final=final,
    )
    rack_compensation = compensation_from_result(
        data,
        fallback_offset={
            'x': float(final.get('x', result.offset_x)),
            'y': float(final.get('y', result.offset_y)),
            'z': float(final.get('z', result.offset_z)),
            'rz': float(final.get('rz', result.offset_rz)),
        },
    )
    opening_rectangle = data.get('opening_rectangle') or None
    transform_context = dict(data.get('transform_context') or {})
    recipe = result.recipe
    if recipe:
        transform_context.setdefault('context_source', 'recipe_current_fallback')
        transform_context.setdefault('capture_pose', dict(recipe.capture_pose or {}))
        transform_context.setdefault('capture_pose_name', recipe.capture_pose_name or '')
        calibration = getattr(recipe, 'hand_eye_calibration', None)
        if calibration and calibration.T_flange_camera:
            transform_context.setdefault('T_flange_camera', calibration.T_flange_camera)
            transform_context.setdefault('hand_eye_calibration_id', calibration.id)
            transform_context.setdefault('hand_eye_calibration_name', calibration.name)
            transform_context.setdefault('hand_eye_source', 'recipe_current_fallback')
        elif recipe.hand_eye_config:
            legacy_hand_eye = recipe.hand_eye_config
            if isinstance(legacy_hand_eye, dict) and legacy_hand_eye.get('matrix') == 'identity':
                legacy_hand_eye = {'matrix': np.eye(4, dtype=float).tolist()}
            transform_context.setdefault('T_flange_camera', legacy_hand_eye)
            transform_context.setdefault('hand_eye_source', 'legacy_recipe_current_fallback')

    camera_rack_compensation = data.get('camera_rack_compensation')
    if not camera_rack_compensation and rack_compensation.get('source') in {
        'local_template_3d', 'local_template_current_baseline',
    }:
        camera_rack_compensation = rack_compensation
    robot_rack_compensation = data.get('robot_rack_compensation')
    measured_layer_spacing = data.get('measured_layer_spacing')
    if measured_layer_spacing is None:
        # Older workbench records stored an explicit JSON null before the
        # layer-spacing measurement became mandatory.  ``dict.get`` does not
        # use its default for an existing null value, so fall back explicitly.
        measured_layer_spacing = result.measured_layer_spacing
    if measured_layer_spacing is None:
        measured_layer_spacing = 0
    robot_delta = {'x': None, 'y': None, 'z': None}
    if robot_rack_compensation:
        robot_pose = robot_rack_compensation.get('pose6d') or {}
        robot_matrix = robot_rack_compensation.get('matrix') or []
        for index, axis in enumerate(('x', 'y', 'z')):
            value = robot_pose.get(axis)
            if value is None and len(robot_matrix) > index and len(robot_matrix[index]) > 3:
                value = robot_matrix[index][3]
            try:
                numeric = float(value)
                robot_delta[axis] = numeric if np.isfinite(numeric) else None
            except (TypeError, ValueError):
                robot_delta[axis] = None
    return {
        'id': result.id,
        'task_id': result.vision_task_id,
        'task_kind': 'RACK_3D_LOCATION',
        'recipe_id': result.recipe_id,
        'recipe_name': recipe.recipe_name if recipe else '',
        'position_no': result.position_no,
        'layer_no': result.layer_no,
        'locate_type': locate_type,
        'layer_index': layer_index,
        'rack_side': result.side,
        'locate_ok': result.is_success,
        'is_success': result.is_success,
        'actual_x': float(result.actual_x),
        'actual_y': float(result.actual_y),
        'actual_z': float(result.actual_z),
        'offset_x': float(result.offset_x),
        'offset_y': float(result.offset_y),
        'offset_z': float(result.offset_z),
        'offset_rz': float(result.offset_rz),
        'overall_offset_x': float(overall.get('x', result.offset_x if locate_type == LOCATE_TYPE_GLOBAL else 0)),
        'overall_offset_y': float(overall.get('y', result.offset_y if locate_type == LOCATE_TYPE_GLOBAL else 0)),
        'overall_offset_z': float(overall.get('z', result.offset_z if locate_type == LOCATE_TYPE_GLOBAL else 0)),
        'overall_offset_rz': float(overall.get('rz', result.offset_rz if locate_type == LOCATE_TYPE_GLOBAL else 0)),
        'layer_offset_x': float(layer.get('x', result.offset_x if locate_type == LOCATE_TYPE_LAYER else 0)),
        'layer_offset_y': float(layer.get('y', result.offset_y if locate_type == LOCATE_TYPE_LAYER else 0)),
        'layer_offset_z': float(layer.get('z', result.offset_z if locate_type == LOCATE_TYPE_LAYER else 0)),
        'layer_offset_rz': float(layer.get('rz', result.offset_rz if locate_type == LOCATE_TYPE_LAYER else 0)),
        'final_offset_x': float(final.get('x', result.offset_x)),
        'final_offset_y': float(final.get('y', result.offset_y)),
        'final_offset_z': float(final.get('z', result.offset_z)),
        'final_offset_rz': float(final.get('rz', result.offset_rz)),
        'measured_layer_spacing': float(measured_layer_spacing),
        'confidence': float(result.confidence),
        'error_code': result.error_code,
        'error_message': result.error_message,
        'raw_data_path': result.raw_data_path,
        'result_image_path': result.result_image_path,
        'result_image_url': result_img.file.url if result_img else '',
        'depth_image_url': depth_img.file.url if depth_img else '',
        'roi_data': result.roi_data or data.get('roi') or {},
        'plc_write_status': result.plc_write_status,
        'plc_error_message': result.plc_error_message,
        'plc_payload': plc_payload,
        'rack_compensation': rack_compensation,
        'camera_rack_compensation': camera_rack_compensation,
        'robot_rack_compensation': robot_rack_compensation,
        'robot_delta_x': robot_delta['x'],
        'robot_delta_y': robot_delta['y'],
        'robot_delta_z': robot_delta['z'],
        'robot_conversion_applied': bool(robot_rack_compensation),
        'compensation_coordinate_system': (
            (camera_rack_compensation or {}).get('coordinate_system')
            or data.get('compensation_coordinate_system')
        ),
        'transform_context': transform_context,
        'compensation_matrix': rack_compensation['matrix'],
        'compensation_pose6d': rack_compensation['pose6d'],
        'robot_compensation_matrix': (
            robot_rack_compensation.get('matrix') if robot_rack_compensation else None
        ),
        'robot_compensation_pose6d': (
            robot_rack_compensation.get('pose6d') if robot_rack_compensation else None
        ),
        'algorithm_version': data.get('algorithm_version') or 'historical',
        'opening_rectangle': opening_rectangle,
        'tcp_verification': data.get('tcp_verification'),
        'result_data': data,
        'created_at': result.created_at.isoformat() if result.created_at else '',
    }
