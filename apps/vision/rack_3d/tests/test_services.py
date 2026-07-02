"""RackPositioningService MOCK 端到端集成测试。Requirements: 26.4

验证完整链路：模拟点云 → 手眼矩阵 → 机器人位姿 → 坐标转换 → ROI 裁剪
→ 三轴定位 → 补偿计算 → 结果落库。
"""

from decimal import Decimal

from django.test import TestCase

from apps.vision.models import (
    RackLocationRecipe,
    RackLocationROI3DEnhanced,
    RackLocationResult,
    ROI3DType,
)
from apps.vision.rack_3d.services import RackPositioningService
from apps.vision.rack_3d.exceptions import ROIError


# MOCK 第 2 层：T_combined 平移 = (1030, 440, 1020)，恒等旋转。
# 相机特征经变换后落点：支撑面 Z≈1220，前边缘 Y≈530，立柱 X≈900。
LAYER = 2
ROIS = {
    ROI3DType.SUPPORT_PLANE: dict(x_min=925, x_max=1135, y_min=375, y_max=505, z_min=1214, z_max=1226),
    ROI3DType.FRONT_EDGE:    dict(x_min=925, x_max=1135, y_min=522, y_max=538, z_min=1214, z_max=1266),
    ROI3DType.PILLAR:        dict(x_min=885, x_max=915,  y_min=380, y_max=400, z_min=1160, z_max=1290),
}


class RackPositioningServiceMockTest(TestCase):
    def setUp(self):
        self.recipe = RackLocationRecipe.objects.create(
            recipe_name='MOCK-Demo-POS1-L2',
            position_no=1,
            layer_no=LAYER,
            layer_count=3,
            standard_x=Decimal('900'),
            standard_y=Decimal('530'),
            standard_z=Decimal('1220'),
            confidence_threshold=Decimal('0.5000'),
        )
        for roi_type, bounds in ROIS.items():
            RackLocationROI3DEnhanced.objects.create(
                recipe=self.recipe,
                roi_name=f'L{LAYER}-{roi_type}',
                roi_type=roi_type,
                position_no=1,
                layer_no=LAYER,
                **{k: Decimal(str(v)) for k, v in bounds.items()},
            )

    def _service(self):
        return RackPositioningService(mode='MOCK', seed=123)

    def test_end_to_end_success_and_persist(self):
        result = self._service().execute_positioning(self.recipe.id, LAYER)

        self.assertTrue(result['is_success'], msg=result.get('error_message'))
        self.assertAlmostEqual(result['actual_z'], 1220, delta=5)
        self.assertAlmostEqual(result['actual_y'], 530, delta=5)
        self.assertAlmostEqual(result['actual_x'], 900, delta=5)
        # 补偿 = 偏移，且接近 0（standard 设为期望实际值）
        self.assertLess(abs(result['offset_z']), 5)
        self.assertEqual(result['compensation_z'], result['offset_z'])

        # 结果落库
        self.assertIn('result_id', result)
        rec = RackLocationResult.objects.get(id=result['result_id'])
        self.assertTrue(rec.is_success)
        self.assertEqual(rec.layer_no, LAYER)
        self.assertIn('z_detection', rec.result_data)

    def test_no_save_when_save_false(self):
        self._service().execute_positioning(self.recipe.id, LAYER, save=False)
        self.assertEqual(RackLocationResult.objects.count(), 0)

    def test_missing_roi_raises(self):
        RackLocationROI3DEnhanced.objects.filter(roi_type=ROI3DType.PILLAR).delete()
        with self.assertRaises(ROIError):
            self._service().execute_positioning(self.recipe.id, LAYER)
