"""视觉服务：创建视觉任务、调用算法、保存结构化结果、做配方容差校验。

流程是否继续由 workflow 根据视觉结果和配方校验共同判断，本服务只产出结果。
"""
from decimal import Decimal
from pathlib import Path

import cv2
from django.utils import timezone

from apps.core.constants import DeviceType, RackSide, ResultStatus, VisionImageType, VisionTaskType
from apps.devices.services import get_device_adapter
from .algorithms.foam_inspector import FoamInspector
from .algorithms.rack_locator import RackLocator
from .models import (
    CalibrationProfile,
    FoamInspectionResult,
    RackLocationResult,
    VisionImage,
    VisionTask,
)


def _within_tolerance(measured, expected, tolerance):
    return abs(Decimal(str(measured)) - Decimal(str(expected))) <= Decimal(str(tolerance))


class VisionService:
    """Coordinates camera capture, OpenCV algorithms, and result persistence."""

    def __init__(self, rack_locator=None, foam_inspector=None, camera_adapter=None):
        self.rack_locator = rack_locator or RackLocator()
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

    def locate_rack(self, product, rack, recipe, side, simulated_offsets=None,
                    min_confidence: float = 0.70):
        """对单侧料架定位并校验层高/层距是否匹配配方。

        3D 深度相机（手眼安装）：机器人携带相机移动至预设拍照位停下后
        固定拍摄，不扫描。方案A：单次拍摄覆盖整个料架（3层）。

        参数：
            min_confidence: 置信度阈值，低于此值视为定位失败（默认 0.70）。
        """
        task = self._new_task(VisionTaskType.RACK_LOCATING, product=product, rack=rack)
        try:
            product_code = getattr(product, 'product_code', '')
            data = self.rack_locator.locate(
                side=side, recipe=recipe, simulated_offsets=simulated_offsets,
                product_code=product_code,
            )

            # 置信度门限校验
            confidence = float(data.get('confidence', 1.0))
            confidence_ok = confidence >= min_confidence

            # 配方层高/层距容差校验（复用算法内 recipe_matched，再用 Decimal 精确比较）
            matched = data.get('recipe_matched', True)
            if recipe is not None and matched:
                matched = (
                    _within_tolerance(
                        data['measured_layer_height'], recipe.layer_height,
                        max(recipe.tolerance_z, Decimal('1')),
                    )
                    and _within_tolerance(
                        data['measured_layer_spacing'], recipe.layer_spacing,
                        max(recipe.tolerance_z, Decimal('1')),
                    )
                )

            is_success = data['is_success'] and matched and confidence_ok

            # 将完整分层数据和 plc_payload 合并进 result_data
            enriched_result_data = {
                **data['result_data'],
                'confidence': confidence,
                'layer_heights': data.get('layer_heights', []),
                'layer_spacings': data.get('layer_spacings', []),
                'plc_payload': data.get('plc_payload', {}),
            }

            result = RackLocationResult.objects.create(
                vision_task=task,
                rack=rack,
                side=side,
                offset_x=data['offset_x'],
                offset_y=data['offset_y'],
                offset_z=data['offset_z'],
                measured_layer_height=data['measured_layer_height'],
                measured_layer_spacing=data['measured_layer_spacing'],
                recipe_layer_height=recipe.layer_height if recipe else 0,
                recipe_layer_spacing=recipe.layer_spacing if recipe else 0,
                is_recipe_matched=matched,
                is_success=is_success,
                result_data=enriched_result_data,
            )
            self._save_images(task, data)
            task.status = ResultStatus.SUCCESS if is_success else ResultStatus.FAILED
            task.finished_at = timezone.now()
            if not is_success:
                reasons = []
                if not confidence_ok:
                    reasons.append(f'置信度不足({confidence:.2%}<{min_confidence:.0%})')
                if not matched:
                    reasons.append(
                        f'配方超差(层高:{data["measured_layer_height"]:.1f}mm '
                        f'层距:{data["measured_layer_spacing"]:.1f}mm)'
                    )
                if not data['is_success']:
                    reasons.append('算法定位失败')
                task.error_message = '料架定位失败: ' + '; '.join(reasons)
            task.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])
            return result
        except Exception as exc:  # noqa: BLE001
            self._fail_task(task, str(exc))
            raise

    def locate_both_racks(self, product, rack, recipe, min_confidence: float = 0.70):
        """阶段三：单次拍摄同时覆盖左右两个料架，返回 (left, right) 结果。

        硬件确认：3D 相机一次拍摄即可覆盖两个并列料架，因此只产生
        一个 VisionTask、一对图像，算法内部分别解析左/右侧数据。
        """
        task = self._new_task(VisionTaskType.RACK_LOCATING, product=product, rack=rack)
        try:
            product_code = getattr(product, 'product_code', '')
            # 单次拍摄：locate_all 内部调用 generate_depth_scene_both 生成宽幅图
            all_data = self.rack_locator.locate_all(
                recipe=recipe,
                product_code=product_code,
            )

            side_results = []
            for side_key in ('LEFT', 'RIGHT'):
                data = all_data[side_key]
                confidence = float(data.get('confidence', 1.0))
                confidence_ok = confidence >= min_confidence

                matched = data.get('recipe_matched', True)
                if recipe is not None and matched:
                    matched = (
                        _within_tolerance(
                            data['measured_layer_height'], recipe.layer_height,
                            max(recipe.tolerance_z, Decimal('1')),
                        )
                        and _within_tolerance(
                            data['measured_layer_spacing'], recipe.layer_spacing,
                            max(recipe.tolerance_z, Decimal('1')),
                        )
                    )
                is_success = data['is_success'] and matched and confidence_ok

                enriched = {
                    **data['result_data'],
                    'confidence': confidence,
                    'layer_heights': data.get('layer_heights', []),
                    'layer_spacings': data.get('layer_spacings', []),
                    'plc_payload': data.get('plc_payload', {}),
                }
                result = RackLocationResult.objects.create(
                    vision_task=task, rack=rack, side=side_key,
                    offset_x=data['offset_x'], offset_y=data['offset_y'],
                    offset_z=data['offset_z'],
                    measured_layer_height=data['measured_layer_height'],
                    measured_layer_spacing=data['measured_layer_spacing'],
                    recipe_layer_height=recipe.layer_height if recipe else 0,
                    recipe_layer_spacing=recipe.layer_spacing if recipe else 0,
                    is_recipe_matched=matched,
                    is_success=is_success,
                    result_data=enriched,
                )
                side_results.append((side_key, result, is_success, confidence, confidence_ok, matched))

            # 单张宽幅图（一次拍摄产出一张图）
            self._save_images(task, {
                'original_image': all_data.get('original_image'),
                'result_image':   all_data.get('result_image'),
                'image_width':    all_data.get('image_width', 0),
                'image_height':   all_data.get('image_height', 0),
            })

            all_success = all(r[2] for r in side_results)
            task.status = ResultStatus.SUCCESS if all_success else ResultStatus.FAILED
            task.finished_at = timezone.now()
            if not all_success:
                msgs = []
                for sk, _, ok, conf, conf_ok, mat in side_results:
                    if not ok:
                        r = []
                        if not conf_ok:
                            r.append(f'置信度不足({conf:.2%})')
                        if not mat:
                            r.append('配方超差')
                        msgs.append(f'{sk}: {"; ".join(r)}')
                task.error_message = '料架定位失败: ' + ' | '.join(msgs)
            task.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])

            left  = next(r[1] for r in side_results if r[0] == 'LEFT')
            right = next(r[1] for r in side_results if r[0] == 'RIGHT')
            return left, right

        except Exception as exc:  # noqa: BLE001
            self._fail_task(task, str(exc))
            raise

    # ------------------------------------------------------------------
    # 泡棉贴附检测
    # ------------------------------------------------------------------

    def inspect_foam(self, product, rack, position_index=0, simulated_pass=True,
                     inspection_config=None, use_camera=False,
                     camera_code='CAM-INSPECT-FOAM-01'):
        """泡棉贴附检测，保存 FoamInspectionResult。

        参数：
            inspection_config: 可选检测配置字典，透传给 FoamInspector.inspect()，
                支持 score_threshold / coverage_threshold / max_offset_px。
        """
        task = self._new_task(VisionTaskType.FOAM_INSPECTION, product=product, rack=rack)
        try:
            image = None
            camera_image_path = ''
            if use_camera:
                adapter = self.camera_adapter or get_device_adapter(
                    device_type=DeviceType.INSPECT_CAMERA
                )
                capture = adapter.capture(camera_code, VisionTaskType.FOAM_INSPECTION)
                camera_image_path = capture.get('image_path') or ''
                if camera_image_path:
                    image_path = Path(camera_image_path)
                    image = cv2.imread(str(image_path))
                    if image is None:
                        raise RuntimeError(f'相机图片读取失败: {image_path}')

            profile, calibration_config = self._foam_calibration_config(camera_code)
            merged_config = {}
            if inspection_config:
                merged_config.update(inspection_config)
            merged_config.update(calibration_config)

            data = self.foam_inspector.inspect(
                position_index=position_index,
                simulated_pass=simulated_pass,
                inspection_config=merged_config or None,
                image=image,
                camera_image_path=camera_image_path,
            )
            if profile:
                data.setdefault('result_data', {})['calibration_profile'] = profile.name
                data['result_data']['calibration_profile_id'] = profile.id
            result = FoamInspectionResult.objects.create(
                vision_task=task,
                product=product,
                rack=rack,
                position_index=position_index,
                is_present=data['is_present'],
                is_aligned=data['is_aligned'],
                has_lifted_edge=data['has_lifted_edge'],
                score=data['score'],
                is_passed=data['is_passed'],
                offset_x_px=data.get('offset_x_px', 0),
                offset_y_px=data.get('offset_y_px', 0),
                coverage_ratio=data.get('coverage_ratio', 0),
                defect_type=data.get('defect_type', 'NONE'),
                result_data=data.get('result_data', {}),
            )
            self._save_images(task, data)
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
