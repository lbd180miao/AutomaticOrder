"""视觉服务：创建视觉任务、调用算法、保存结构化结果、做配方容差校验。

流程是否继续由 workflow 根据视觉结果和配方校验共同判断，本服务只产出结果。
"""
from decimal import Decimal

from django.utils import timezone

from apps.core.constants import RackSide, ResultStatus, VisionImageType, VisionTaskType
from .algorithms.foam_inspector import FoamInspector
from .algorithms.rack_locator import RackLocator
from .models import FoamInspectionResult, RackLocationResult, VisionImage, VisionTask


def _within_tolerance(measured, expected, tolerance):
    return abs(Decimal(str(measured)) - Decimal(str(expected))) <= Decimal(str(tolerance))


class VisionService:
    """Coordinates camera capture, OpenCV algorithms, and result persistence."""

    def __init__(self, rack_locator=None, foam_inspector=None):
        self.rack_locator = rack_locator or RackLocator()
        self.foam_inspector = foam_inspector or FoamInspector()

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

    # ------------------------------------------------------------------
    # 料架定位
    # ------------------------------------------------------------------

    def locate_rack(self, product, rack, recipe, side, simulated_offsets=None):
        """对单侧料架定位并校验层高/层距是否匹配配方。"""
        task = self._new_task(VisionTaskType.RACK_LOCATING, product=product, rack=rack)
        try:
            data = self.rack_locator.locate(
                side=side, recipe=recipe, simulated_offsets=simulated_offsets,
            )
            matched = True
            if recipe is not None:
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
                is_success=data['is_success'] and matched,
                result_data=data['result_data'],
            )
            self._save_images(task, data)
            task.status = ResultStatus.SUCCESS if result.is_success else ResultStatus.FAILED
            task.finished_at = timezone.now()
            if not result.is_success:
                task.error_message = '料架定位或配方校验未通过'
            task.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])
            return result
        except Exception as exc:  # noqa: BLE001 - 记录失败并向上抛
            self._fail_task(task, str(exc))
            raise

    def locate_both_racks(self, product, rack, recipe):
        """阶段三：左右料架分别定位，返回 (left, right) 结果。"""
        left = self.locate_rack(product, rack, recipe, RackSide.LEFT)
        right = self.locate_rack(product, rack, recipe, RackSide.RIGHT)
        return left, right

    # ------------------------------------------------------------------
    # 泡棉贴附检测
    # ------------------------------------------------------------------

    def inspect_foam(self, product, rack, position_index=0, simulated_pass=True,
                     inspection_config=None):
        """泡棉贴附检测，保存 FoamInspectionResult。

        参数：
            inspection_config: 可选检测配置字典，透传给 FoamInspector.inspect()，
                支持 score_threshold / coverage_threshold / max_offset_px。
        """
        task = self._new_task(VisionTaskType.FOAM_INSPECTION, product=product, rack=rack)
        try:
            data = self.foam_inspector.inspect(
                position_index=position_index,
                simulated_pass=simulated_pass,
                inspection_config=inspection_config,
            )
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
                result_data=data['result_data'],
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
