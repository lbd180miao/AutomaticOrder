"""视觉服务：创建视觉任务、调用算法、保存结构化结果、做配方容差校验。

流程是否继续由 workflow 根据视觉结果和配方校验共同判断，本服务只产出结果。
"""
import logging
import time
from decimal import Decimal
from pathlib import Path

import cv2
from django.utils import timezone

from apps.core.constants import DeviceType, RackSide, ResultStatus, VisionImageType, VisionTaskType
from apps.devices.services import get_device_adapter
from .algorithms.foam_inspector import FoamInspector
from .models import (
    CalibrationProfile,
    FoamInspectionResult,
    RackLocationResult,
    VisionImage,
    VisionRecipe,
    VisionTask,
)
from .recipe_utils import (
    build_foam_inspection_config,
    get_active_foam_2d_recipe_by_pos,
    serialize_recipe,
)


logger = logging.getLogger(__name__)


class FoamRecipeConfigurationError(ValueError):
    """The selected foam recipe cannot be used for inspection."""


def _within_tolerance(measured, expected, tolerance):
    return abs(Decimal(str(measured)) - Decimal(str(expected))) <= Decimal(str(tolerance))


class VisionService:
    """Coordinates camera capture, OpenCV algorithms, and result persistence."""

    def __init__(self, rack_locator=None, foam_inspector=None, camera_adapter=None):
        self.rack_locator = rack_locator
        self.foam_inspector = foam_inspector or FoamInspector()
        self.camera_adapter = camera_adapter

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _new_task(self, task_type, product=None, rack=None):
        return VisionTask.objects.create(
            task_type=task_type,
            product=product,
            rack=rack,
            status=ResultStatus.RUNNING,
            started_at=timezone.now(),
        )

    def _save_images(self, task, data):
        """把算法返回的原图/结果图登记为 VisionImage 记录。"""
        w = data.get('image_width', 0)
        h = data.get('image_height', 0)
        if data.get('original_image'):
            VisionImage.objects.create(
                vision_task=task, image_type=VisionImageType.ORIGINAL,
                file=data['original_image'], width=w, height=h,
                captured_at=timezone.now(),
            )
        if data.get('result_image'):
            VisionImage.objects.create(
                vision_task=task, image_type=VisionImageType.RESULT,
                file=data['result_image'], width=w, height=h,
                captured_at=timezone.now(),
            )

    def _fail_task(self, task, message):
        """统一将任务标记为失败，消除重复的 except 块逻辑。"""
        task.status = ResultStatus.FAILED
        task.finished_at = timezone.now()
        task.error_message = message
        task.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])

    def _foam_calibration_config(self, camera_code):
        profile = (
            CalibrationProfile.objects
            .filter(device_code=camera_code, version='foam-roi-v1', is_active=True)
            .order_by('-updated_at')
            .first()
        )
        if not profile:
            return None, {}
        transform_data = profile.transform_data or {}
        config = {}
        thresholds = transform_data.get('thresholds') or {}
        if isinstance(thresholds, dict):
            config.update(thresholds)
        if transform_data.get('foam_rois'):
            config['foam_rois'] = transform_data['foam_rois']
        return profile, config

    # ------------------------------------------------------------------
    # 料架定位
    # ------------------------------------------------------------------



    # ------------------------------------------------------------------
    # 泡棉贴附检测
    # ------------------------------------------------------------------

    def locate_rack(self, product, rack, recipe, side, simulated_offsets=None, min_confidence=.70):
        from .models import RackLocationRecipe
        from .rack_location import RackLocationService
        location_recipe = recipe if isinstance(recipe, RackLocationRecipe) else getattr(recipe, 'rack_location_recipe', None)
        if location_recipe is None and hasattr(recipe, 'vision_mappings'):
            mappings = recipe.vision_mappings.filter(enabled=True, rack_location_recipe__enabled=True,
                                                       rack_location_recipe__rack_side__in=(side, 'BOTH'))
            if mappings.count() == 1:
                location_recipe = mappings.select_related('rack_location_recipe').get().rack_location_recipe
        if location_recipe is None:
            raise ValueError('请为生产配方绑定已保存点云模板的 3D 定位配方')
        return RackLocationService().trigger(
            recipe_id=location_recipe.pk, position_no=location_recipe.position_no,
            layer_no=location_recipe.layer_no, rack_side=side, product=product, rack=rack,
        )

    def locate_both_racks(self, product, rack, recipe, min_confidence=.70):
        return tuple(self.locate_rack(product, rack, recipe, side, min_confidence=min_confidence)
                     for side in ('LEFT', 'RIGHT'))

    def _foam_recipe_config(self, recipe_id, position_index, require_ready_recipe):
        try:
            if recipe_id:
                recipes = VisionRecipe.objects.filter(recipe_type='FOAM_2D')
                if require_ready_recipe:
                    recipes = recipes.filter(is_active=True)
                recipe = recipes.filter(pk=recipe_id).first()
                if recipe is None:
                    raise ValueError('指定的 2D 泡棉配方不可用')
            else:
                recipe = get_active_foam_2d_recipe_by_pos(position_index)
            config = build_foam_inspection_config(recipe) if recipe else {}
            if require_ready_recipe and not config.get('standard_template_ready'):
                raise ValueError(config.get('standard_template_error') or '请先完成 2D 泡棉配方示教')
            return recipe, config
        except (TypeError, ValueError) as exc:
            raise FoamRecipeConfigurationError(str(exc)) from exc

    def inspect_foam(self, product, rack, position_index=0, simulated_pass=True,
                     inspection_config=None, use_camera=False,
                     camera_code='CAM-INSPECT-FOAM-01',
                     recipe_id=None, use_recipe=True, captured_image_path=None, *,
                     require_ready_recipe=False):
        """泡棉贴附检测，保存 FoamInspectionResult。

        参数：
            inspection_config: 可选检测配置字典，透传给 FoamInspector.inspect()，
                支持 score_threshold / coverage_threshold / max_offset_px。
        """
        pipeline_started = time.perf_counter()
        task = self._new_task(VisionTaskType.FOAM_INSPECTION, product=product, rack=rack)
        timings_ms = {
            'task_create': round((time.perf_counter() - pipeline_started) * 1000, 1),
        }
        try:
            phase_started = time.perf_counter()
            recipe, recipe_config = (self._foam_recipe_config(recipe_id, position_index, require_ready_recipe)
                                     if use_recipe else (None, {}))
            recipe_config_ms = (time.perf_counter() - phase_started) * 1000
            image = None
            camera_image_path = ''
            if use_camera:
                if captured_image_path:
                    # 实时预览刚取得的是同一台相机的全分辨率原图，直接复用，
                    # 避免点击检测后再次完成一轮打开/拍照/关闭相机。
                    camera_image_path = str(captured_image_path)
                    timings_ms['camera_request'] = 0.0
                    timings_ms['preview_frame_reused'] = 1
                else:
                    phase_started = time.perf_counter()
                    adapter = self.camera_adapter or get_device_adapter(
                        device_type=DeviceType.INSPECT_CAMERA
                    )
                    capture = adapter.capture(camera_code, VisionTaskType.FOAM_INSPECTION)
                    timings_ms['camera_request'] = round(
                        (time.perf_counter() - phase_started) * 1000,
                        1,
                    )
                    timings_ms.update(capture.get('timings_ms') or {})
                    camera_image_path = capture.get('image_path') or ''
                    if require_ready_recipe and not camera_image_path:
                        raise RuntimeError(capture.get('error') or '2D 相机未返回采集图像')
                if camera_image_path:
                    phase_started = time.perf_counter()
                    image_path = Path(camera_image_path)
                    image = cv2.imread(str(image_path))
                    if image is None:
                        raise RuntimeError(f'相机图片读取失败: {image_path}')
                    timings_ms['image_decode'] = round(
                        (time.perf_counter() - phase_started) * 1000,
                        1,
                    )

            phase_started = time.perf_counter()
            profile, calibration_config = self._foam_calibration_config(camera_code)
            merged_config = {}
            if inspection_config:
                merged_config.update(inspection_config)
            merged_config.update(calibration_config)
            merged_config.update(recipe_config)
            timings_ms['config_load'] = round(
                recipe_config_ms + (time.perf_counter() - phase_started) * 1000,
                1,
            )

            phase_started = time.perf_counter()
            data = self.foam_inspector.inspect(
                position_index=position_index,
                simulated_pass=simulated_pass,
                inspection_config=merged_config or None,
                image=image,
                camera_image_path=camera_image_path,
            )
            timings_ms['algorithm_and_archive'] = round(
                (time.perf_counter() - phase_started) * 1000,
                1,
            )
            if profile:
                data.setdefault('result_data', {})['calibration_profile'] = profile.name
                data['result_data']['calibration_profile_id'] = profile.id
            if recipe:
                data.setdefault('result_data', {})['recipe'] = serialize_recipe(recipe)
            timings_ms['before_persist_total'] = round(
                (time.perf_counter() - pipeline_started) * 1000,
                1,
            )
            data.setdefault('result_data', {})['timings_ms'] = timings_ms
            persist_started = time.perf_counter()
            result = FoamInspectionResult.objects.create(
                vision_task=task,
                product=product,
                rack=rack,
                position_index=position_index,
                is_present=data['is_present'],
                is_aligned=data['is_aligned'],
                has_lifted_edge=data.get('has_lifted_edge', False),
                score=data['score'],
                is_passed=data['is_passed'],
                offset_x_px=data.get('offset_x_px', 0),
                offset_y_px=data.get('offset_y_px', 0),
                offset_x_mm=data.get('offset_x_mm', 0),
                offset_y_mm=data.get('offset_y_mm', 0),
                coverage_ratio=data.get('coverage_ratio', 0),
                defect_type=data.get('defect_type', 'NONE'),
                result_data=data.get('result_data', {}),
            )
            from .foam_archive import archive
            archive(result, data)
            task.status = ResultStatus.SUCCESS if result.is_passed else ResultStatus.FAILED
            task.finished_at = timezone.now()
            if not result.is_passed:
                # 失败消息携带量化细节，方便排查
                defect = data['result_data'].get('defect_type', '')
                ox = data.get('offset_x_px', 0)
                oy = data.get('offset_y_px', 0)
                cov = data.get('coverage_ratio', 0)
                task.error_message = (
                    f'泡棉检测不合格 [缺陷:{defect}] '
                    f'偏移({ox:+.0f}px,{oy:+.0f}px) 覆盖率:{cov:.1%}'
                )
            task.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])
            timings_ms['persistence'] = round(
                (time.perf_counter() - persist_started) * 1000,
                1,
            )
            timings_ms['total'] = round(
                (time.perf_counter() - pipeline_started) * 1000,
                1,
            )
            logger.info(
                'Foam inspection timing task=%s pos=%s timings_ms=%s',
                task.id,
                position_index,
                timings_ms,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            self._fail_task(task, str(exc))
            raise

    def inspect_foam_all_positions(self, product, rack, position_count,
                                   simulated_pass=True, inspection_config=None):
        """批量检测所有泡棉贴附位置。

        参数：
            position_count: 需检测的贴附位置总数（通常来自配方）。
            simulated_pass: 模拟模式下的通过/失败控制（True = 全部合格）。
            inspection_config: 透传给每次 inspect_foam() 的检测配置。

        返回：
            dict with keys:
                - results: list[FoamInspectionResult]（按位置顺序）
                - all_passed: bool
                - failed_positions: list[int]（不合格的 position_index 列表）
        """
        results = []
        failed_positions = []

        for idx in range(position_count):
            result = self.inspect_foam(
                product=product,
                rack=rack,
                position_index=idx,
                simulated_pass=simulated_pass,
                inspection_config=inspection_config,
            )
            results.append(result)
            if not result.is_passed:
                failed_positions.append(idx)

        return {
            'results': results,
            'all_passed': len(failed_positions) == 0,
            'failed_positions': failed_positions,
        }
