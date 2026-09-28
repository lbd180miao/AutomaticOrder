from django.test import SimpleTestCase
import numpy as np
from .algorithms.foam_inspector import _inspect_calibrated_sides


class LayerFoamTests(SimpleTestCase):
    def config(self):
        return dict(layer_search_roi=[0, .1, 1, .7],
                    standard_masks={side: np.full((20, 30), 255, np.uint8)
                                    for side in ('left', 'right')},
                    coverage_threshold=.75, mm_per_pixel_x=.5,
                    mm_per_pixel_y=.25, max_offset_mm=2,
                    require_standard_template=True)

    def inspect(self, left=True, right=True, shift=0):
        image = np.zeros((200, 300, 3), np.uint8)
        if left:
            image[50:70, 30+shift:60+shift] = 220
        if right:
            image[50:70, 210:240] = 220
        image[160:180, 30:60] = 220  # Different rack layer must be ignored.
        return _inspect_calibrated_sides(image,
            dict(left=[.1,.25,.2,.35], right=[.7,.25,.8,.35]), 0, self.config())

    def test_nominal(self):
        result, _, _, sides = self.inspect()
        self.assertTrue(result['is_passed'])
        self.assertEqual(sides['left']['offset_x_mm'], 0)

    def test_shift_outside_standard_box_is_present_and_measured(self):
        result, roi, _, sides = self.inspect(shift=45)
        self.assertTrue(result['is_present'])
        self.assertFalse(result['is_aligned'])
        self.assertEqual(sides['left']['offset_x_mm'], 22.5)
        self.assertEqual(sides['left']['box'], (75, 50, 105, 70))
        self.assertEqual(sides['left']['mask'].shape, (120, 300))
        self.assertEqual(roi, (0, 20, 300, 140))

    def test_one_component_cannot_satisfy_both_sides(self):
        result, _, _, sides = self.inspect(left=False)
        self.assertFalse(result['is_present'])
        self.assertFalse(sides['left']['is_present'])
        self.assertTrue(sides['right']['is_present'])

    def test_other_layer_is_ignored(self):
        result, _, _, _ = self.inspect(left=False, right=False)
        self.assertFalse(result['is_present'])

    def test_connected_foams_are_assigned_to_both_standards(self):
        image = np.zeros((200,300,3), np.uint8)
        image[50:70,30:60] = 220
        image[50:70,210:240] = 220
        image[58:62,60:210] = 220
        result, _, _, sides = _inspect_calibrated_sides(image,
            dict(left=[.1,.25,.2,.35], right=[.7,.25,.8,.35]), 0, self.config())
        self.assertTrue(result['is_present'])
        self.assertEqual(sides['left']['coverage_ratio'], 1)
        self.assertEqual(sides['right']['coverage_ratio'], 1)

    def test_coverage_and_offset_both_required(self):
        result, _, _, sides = self.inspect(shift=3)
        self.assertTrue(result['is_passed'])  # 90% overlap, 1.5mm offset
        self.assertEqual(sides['left']['coverage_ratio'], .9)
        result, _, _, sides = self.inspect(shift=9)
        self.assertFalse(result['is_passed'])  # 70% overlap, 4.5mm offset
        self.assertTrue(result['is_present'])
        self.assertFalse(sides['left']['is_complete'])

    def test_layer_polygon_excludes_foreground_outside_shape(self):
        image = np.zeros((200,300,3), np.uint8)
        image[50:70,30:60] = 220
        image[50:70,210:240] = 220
        image[90:120,120:180] = 220
        cfg = self.config()
        cfg['layer_search_polygon'] = [[0,.1],[1,.1],[1,.7],[.7,.7],[.7,.4],[0,.4]]
        result, _, _, sides = _inspect_calibrated_sides(image,
            dict(left=[.1,.25,.2,.35], right=[.7,.25,.8,.35]), 0, cfg)
        self.assertTrue(result['is_passed'])
        self.assertEqual(sum(d['detected_pixels'] for d in sides.values()), 1200)

    def test_polygon_not_containing_standards_returns_missing(self):
        cfg = self.config()
        cfg['layer_search_polygon'] = [[0,.1],[1,.1],[1,.2],[0,.2]]
        image = np.zeros((200,300,3), np.uint8)
        image[50:70,30:60] = 220
        image[50:70,210:240] = 220
        result, _, _, sides = _inspect_calibrated_sides(image,
            dict(left=[.1,.25,.2,.35], right=[.7,.25,.8,.35]), 0, cfg)
        self.assertFalse(result['is_present'])
        self.assertFalse(result['is_passed'])
        for side in sides.values():
            self.assertEqual(side['reason'], 'no_foam_detected')
            self.assertEqual(side['coverage_ratio'], 0)
            self.assertEqual(side['standard_pixels'], 600)

    def test_polygon_partial_reference_uses_full_standard_area(self):
        cfg = self.config()
        cfg['layer_search_polygon'] = [[0,.1],[1,.1],[1,.3],[0,.3]]
        image = np.zeros((200,300,3), np.uint8)
        image[50:70,30:60] = 220
        image[50:70,210:240] = 220
        result, _, _, sides = _inspect_calibrated_sides(image,
            dict(left=[.1,.25,.2,.35], right=[.7,.25,.8,.35]), 0, cfg)
        self.assertTrue(result['is_present'])
        self.assertFalse(result['is_passed'])
        self.assertAlmostEqual(sides['left']['coverage_ratio'], .55)
        self.assertEqual(sides['left']['standard_pixels'], 600)

    def test_invalid_layer_rejected(self):
        cfg = self.config()
        cfg['layer_search_roi'] = [0, 0, .15, .7]
        with self.assertRaises(ValueError):
            _inspect_calibrated_sides(np.zeros((200,300,3), np.uint8),
                dict(left=[.1,.25,.2,.35], right=[.7,.25,.8,.35]), 0, cfg)


class LayerStandardTemplateTests(SimpleTestCase):
    def extract(self, image, layer_mode):
        import tempfile
        from types import SimpleNamespace
        from .algorithms.standard_mask_manager import StandardMaskManager
        recipe = SimpleNamespace(image_width=100, image_height=100,
            roi_config={'rightFoamROI': dict(x=20, y=20, width=40, height=40)})
        cfg = {'layer_search_roi': [0, 0, 1, 1]} if layer_mode else {}
        with tempfile.TemporaryDirectory() as folder:
            return StandardMaskManager(folder)._extract_side(image, recipe, 'right', cfg)

    def test_tight_standard_box_accepts_full_foam_in_layer_mode(self):
        image = np.zeros((100, 100, 3), np.uint8)
        image[20:60, 20:60] = 220
        result = self.extract(image, True)
        self.assertEqual(result['coverage_ratio'], 1)
        self.assertEqual(result['pixels'], 1600)
        self.assertEqual(result['centroid_x'], 19.5)

    def test_legacy_search_box_retains_saturation_guard(self):
        image = np.full((100, 100, 3), 220, np.uint8)
        with self.assertRaisesRegex(ValueError, '占满搜索框'):
            self.extract(image, False)

    def test_layer_mode_still_rejects_missing_foam(self):
        with self.assertRaisesRegex(ValueError, '未识别到泡棉'):
            self.extract(np.zeros((100, 100, 3), np.uint8), True)
