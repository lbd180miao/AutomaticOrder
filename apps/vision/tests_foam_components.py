"""Regression coverage for layer component splitting and noise handling."""
from unittest import TestCase
import cv2
import numpy as np
from .algorithms.foam_inspector import _inspect_layer_sides


class LayerComponentTests(TestCase):
    def run_case(self, joined=False, noise=False):
        image = np.zeros((180, 320, 3), np.uint8)
        image[60:100, 50:100] = 200
        image[60:100, 210:260] = 200
        if joined:
            image[76:84, 100:210] = 200
        if noise:
            for y in range(12, 160, 16):
                for x in range(12, 300, 16):
                    if 48 <= y <= 112:
                        continue
                    image[y:y+4, x:x+4] = 200
        rois = {'left': [50/320, 60/180, 100/320, 100/180],
                'right': [210/320, 60/180, 260/320, 100/180]}
        cfg = {'layer_search_roi': [0, 0, 1, 1],
               'standard_masks': {s: np.full((40, 50), 255, np.uint8) for s in rois}}
        return _inspect_layer_sides(image, rois, cfg)

    def test_noise_does_not_change_selected_foams(self):
        clean, noisy = self.run_case(), self.run_case(noise=True)
        for side in clean:
            np.testing.assert_array_equal(clean[side]['mask'], noisy[side]['mask'])
            self.assertEqual(clean[side]['coverage_ratio'], 1)

    def test_connected_foams_are_split_into_distinct_sides(self):
        sides = self.run_case(joined=True, noise=True)
        left, right = sides['left']['mask'], sides['right']['mask']
        self.assertFalse(np.any((left > 0) & (right > 0)))
        for side in sides.values():
            self.assertEqual(side['coverage_ratio'], 1)
            self.assertTrue(side['is_present'])
        self.assertLess(np.nonzero(left)[1].mean(), np.nonzero(right)[1].mean())


class UnifiedTeachingTests(TestCase):
    def test_reference_self_check_translation_and_missing(self):
        import tempfile
        from types import SimpleNamespace
        from .algorithms.standard_mask_manager import StandardMaskManager
        from .algorithms.foam_inspector import _resolve_side_roi_config
        image = np.zeros((180, 320, 3), np.uint8)
        image[60:100, 50:100] = 200
        image[60:100, 210:260] = 200
        # Internal holes must not be filled only during teaching.
        image[70:80, 65:75] = 0
        roi = {'left': [40/320, 50/180, 110/320, 110/180],
               'right': [200/320, 50/180, 270/320, 110/180]}
        recipe = SimpleNamespace(pk=1, pos=0, image_width=320, image_height=180, roi_config={
            'leftFoamROI': {}, 'rightFoamROI': {}})
        cfg = {'layer_search_roi': [0, 0, 1, 1], 'foam_rois': {'0': roi},
               'mm_per_pixel_x': 1, 'mm_per_pixel_y': 1,
               'max_offset_mm': 4, 'max_offset_x_mm': 4, 'max_offset_y_mm': 4}
        with tempfile.TemporaryDirectory() as directory:
            manager = StandardMaskManager(directory)
            extracted = manager._extract_layer_set(image, recipe, cfg)
            template = manager.create_set_from_sample(image, recipe, 'test', cfg)
            self.assertTrue(template['self_check_passed'])
            self.assertEqual(template['mask_space'], 'layer-v3')
            from pathlib import Path
            source = cv2.imread(str(Path(directory) / Path(template['source_image_path']).name))
            np.testing.assert_array_equal(source, image)
            disk_cfg = dict(cfg, standard_mask_space='layer-v3', standard_mask_paths={
                side: str(Path(directory) / Path(template['sides'][side]['path']).name)
                for side in ('left', 'right')})
            for data in _inspect_layer_sides(source, roi, disk_cfg).values():
                self.assertEqual(data['coverage_ratio'], 1)
                self.assertEqual(data['offset_x_px'], 0)
                self.assertEqual(data['offset_y_px'], 0)
        cfg.update(standard_mask_space='layer-v3',
                   standard_masks={k: v['mask'] for k, v in extracted.items()})
        def inspect(img):
            return _inspect_layer_sides(img, _resolve_side_roi_config(cfg, 0), cfg)
        for data in inspect(image).values():
            self.assertEqual(data['coverage_ratio'], 1)
            self.assertEqual(data['offset_x_px'], 0)
            self.assertEqual(data['offset_y_px'], 0)
            self.assertTrue(data['is_aligned'])
        shifted = cv2.warpAffine(image, np.float32([[1, 0, 12], [0, 1, 7]]), (320, 180))
        for data in inspect(shifted).values():
            self.assertAlmostEqual(data['offset_x_px'], 12, places=2)
            self.assertAlmostEqual(data['offset_y_px'], 7, places=2)
            self.assertFalse(data['is_aligned'])
        for data in inspect(np.zeros_like(image)).values():
            self.assertFalse(data['is_present'])
