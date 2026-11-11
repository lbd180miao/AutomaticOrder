"""Quality regressions: missing material must not be hidden by stable centroids."""
import json
from unittest import TestCase
from unittest.mock import patch

import cv2
import numpy as np
from django.test import SimpleTestCase

from .algorithms.foam_quality import measure_integrity, quality_config
from .algorithms.foam_inspector import (
    _detect_foam_side, _inspect_calibrated_sides, _shadow_layer_mask,
    _apply_image_quality_adjustments,
)
from .models import VisionRecipe
from .recipe_utils import build_foam_inspection_config, get_foam_standard_template_status


class FoamQualityTests(TestCase):
    def setUp(self):
        self.standard = np.zeros((120, 200), np.uint8)
        self.standard[40:80, 60:140] = 255
        self.image = np.zeros((120, 200, 3), np.uint8)
        self.cfg = {
            'layer_search_roi': [0, 0, 1, 1], 'standard_masks': {'left': self.standard},
            'ignore_border_ratio': 0, 'coverage_threshold': .3,
            'decision_mode': 'separated-v2', 'min_area_ratio': .8,
            'max_area_ratio': 1.25, 'max_missing_ratio': .2,
            'max_excess_ratio': .25, 'max_offset_x_px': 15, 'max_offset_y_px': 10,
        }

    def detect(self, mask, **kwargs):
        return _detect_foam_side(self.image, (0, 0, 200, 120),
                                 dict(self.cfg, _detected_mask=mask, **kwargs), side='left')

    def test_symmetric_missing_material_fails_despite_unchanged_centroid(self):
        mask = self.standard.copy()
        mask[:, :84] = 0
        mask[:, 116:] = 0
        result = self.detect(mask)
        self.assertAlmostEqual(result['offset_x_px'], 0)
        self.assertTrue(result['is_aligned'])
        self.assertGreater(result['coverage_ratio'], .3)
        self.assertFalse(result['is_complete'])
        self.assertIn('area_below_minimum', result['quality_failures'])

    def test_translation_does_not_become_missing_but_offset_still_fails(self):
        shifted = cv2.warpAffine(self.standard, np.float32([[1, 0, 30], [0, 1, 0]]), (200, 120))
        result = self.detect(shifted)
        self.assertTrue(result['is_complete'])
        self.assertFalse(result['is_aligned'])
        self.assertEqual(result['quality_failures'], ['misaligned'])
        self.assertEqual(result['integrity']['aligned_coverage_ratio'], 1)
        # Legacy coverage remains available and is not silently redefined.
        self.assertAlmostEqual(result['coverage_ratio'], .625)

    def test_within_tolerance_translation_passes_integrity(self):
        shifted = cv2.warpAffine(self.standard, np.float32([[1, 0, 10], [0, 1, 5]]), (200, 120))
        result = self.detect(shifted)
        self.assertTrue(result['is_complete'])
        self.assertTrue(result['is_aligned'])

    def test_giant_reflection_cannot_pass_on_overlap_alone(self):
        result = self.detect(np.full_like(self.standard, 255))
        self.assertEqual(result['coverage_ratio'], 1)
        self.assertFalse(result['is_complete'])
        self.assertIn('area_above_maximum', result['quality_failures'])
        self.assertIn('excess_area', result['quality_failures'])

    def test_excess_outside_aligned_canvas_is_not_hidden(self):
        detected = self.standard.copy()
        detected[:, :40] = 255
        metrics = measure_integrity(detected, self.standard)
        self.assertGreater(metrics['excess_ratio'], 1)

    def test_local_hole_is_detected_without_filling(self):
        mask = self.standard.copy()
        mask[42:57, 64:84] = 0
        result = self.detect(mask, max_local_missing_ratio=.1)
        self.assertIn('local_defect', result['quality_failures'])
        np.testing.assert_array_equal(result['mask'], mask)

    def test_legacy_limits_are_preserved(self):
        mask = self.standard.copy()
        mask[:, :84] = 0
        mask[:, 116:] = 0
        cfg = {k: v for k, v in self.cfg.items() if k not in (
            'min_area_ratio', 'max_area_ratio', 'max_missing_ratio', 'max_excess_ratio')}
        cfg.update(decision_mode='legacy', _detected_mask=mask)
        result = _detect_foam_side(self.image, (0, 0, 200, 120), cfg, side='left')
        self.assertTrue(result['is_complete'])
        self.assertEqual(result['integrity']['area_ratio'], .4)

    def test_bad_quality_never_relaxes_acceptance(self):
        cfg = {'coverage_threshold': .3, 'enable_auto_adjustment': True}
        result = _apply_image_quality_adjustments(cfg, {'suggestions': {
            'coverage_threshold_adjust': -.02, 'use_clahe': True}})
        self.assertEqual(result['coverage_threshold'], .3)
        self.assertEqual(cfg['coverage_threshold'], .3)

    def test_invalid_limits_cannot_silently_pass(self):
        for cfg in ({'decision_mode': 'separated-v2'}, {'min_area_ratio': float('nan')},
                    {'max_missing_ratio': 1.1}, {'min_area_ratio': 2, 'max_area_ratio': 1}):
            with self.subTest(cfg=cfg), self.assertRaises(ValueError):
                quality_config(cfg)

    def test_aggregated_failures_preserved_in_json(self):
        rois = {'left': [.3, 1/3, .7, 2/3], 'right': [.3, 1/3, .7, 2/3]}
        good = self.detect(self.standard)
        bad = self.detect(np.full_like(self.standard, 255))
        with patch('apps.vision.algorithms.foam_inspector._inspect_layer_sides',
                   return_value={'left': good, 'right': bad}):
            result, *_ = _inspect_calibrated_sides(self.image, rois, 0, self.cfg)
        self.assertFalse(result['is_passed'])
        self.assertFalse(result['is_complete'])
        self.assertEqual(result['inspection_status'], 'FAIL')
        self.assertIn('excess_area', result['quality_failures']['right'])
        json.dumps(result)

    def test_saturated_untemplated_image_is_invalid_and_cannot_pass(self):
        image = np.full((100, 200, 3), 255, np.uint8)
        rois = {'left': [0, 0, .5, 1], 'right': [.5, 0, 1, 1]}
        result, *_ = _inspect_calibrated_sides(image, rois, 0, {})
        self.assertEqual(result['inspection_status'], 'INVALID')
        self.assertFalse(result['is_passed'])
        self.assertIn('mask_saturated', result['quality_failures']['left'])


class GraySegmentationTests(TestCase):
    def test_uniform_gray_without_white_highlight_and_true_hole(self):
        image = np.full((180, 320, 3), 20, np.uint8)
        references = {}
        for side, x in (('left', 40), ('right', 200)):
            image[50:130, x:x+70] = 90
            image[95:115, x+20:x+40] = 20
            references[side] = np.zeros((180, 320), np.uint8)
            references[side][45:135, x-5:x+75] = 255
        self.assertFalse(np.any(_shadow_layer_mask(image, references, 512, 3)))
        mask = _shadow_layer_mask(image, references, 1024, 3, adaptive_gray=True)
        self.assertGreater(np.mean(mask[50:90, 40:110] > 0), .95)
        self.assertFalse(np.any(mask[95:115, 60:80]))
        self.assertFalse(np.any(mask[:35]))
        # A missing left foam must not be filled from its reference geometry.
        image[:, :160] = 20
        mask = _shadow_layer_mask(image, references, 1024, 3, adaptive_gray=True)
        self.assertFalse(np.any(mask[:, :160]))
        self.assertGreater(np.count_nonzero(mask[:, 200:270]), 4000)
        self.assertFalse(np.any(_shadow_layer_mask(np.full_like(image, 90), references,
                                                   1024, 3, adaptive_gray=True)))


class QualityRecipeTests(SimpleTestCase):
    def recipe(self):
        return VisionRecipe(pos=0, image_width=200, image_height=120, roi_config={
            'leftFoamROI': {'x': 20, 'y': 20, 'width': 40, 'height': 40},
            'rightFoamROI': {'x': 120, 'y': 20, 'width': 40, 'height': 40},
            'layerSearchROI': {'x': 0, 'y': 0, 'width': 200, 'height': 120},
        })

    def test_config_propagates_and_material_change_keeps_roi_standard(self):
        recipe = self.recipe()
        recipe.algorithm_config = {'material_type': 'gray', 'foam_segmentation': 'gray-graphcut-v3'}
        recipe.threshold_config = {'decision_mode': 'separated-v2', 'min_area_ratio': .8,
                                  'max_area_ratio': 1.2, 'max_missing_ratio': .2,
                                  'max_excess_ratio': .2}
        cfg = build_foam_inspection_config(recipe)
        self.assertEqual(cfg['material_type'], 'gray')
        self.assertEqual(cfg['foam_segmentation'], 'gray-graphcut-v3')
        self.assertEqual(cfg['min_area_ratio'], .8)
        recipe.standard_template_config = {'configured_foam_segmentation': 'gray-graphcut-v3',
                                           'material_type': 'white'}
        status = get_foam_standard_template_status(recipe)
        self.assertTrue(status['ready'])
        self.assertEqual(status['reason'], '')
        self.assertTrue(build_foam_inspection_config(recipe)['standard_from_roi'])

    def test_invalid_segmentation_threshold_is_rejected(self):
        recipe = self.recipe()
        for value in (float('nan'), 300, -1, 10.5):
            recipe.algorithm_config = {'segmentation_config': {'foam_min_v': value}}
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_foam_inspection_config(recipe)

    def test_roi_is_standard_without_files_and_ignores_old_algorithm(self):
        from .algorithms.foam_inspector import _inspect_layer_sides
        recipe = self.recipe()
        recipe.standard_template_config = {'foam_segmentation': 'shadow-graphcut-fast-v2'}
        image = np.zeros((120, 200, 3), np.uint8)
        image[20:60, 20:60] = 240
        image[20:60, 120:160] = 240
        for material in ('white', 'gray'):
            recipe.algorithm_config = {'material_type': material, 'foam_segmentation': 'fixed-threshold'}
            cfg = build_foam_inspection_config(recipe)
            self.assertTrue(cfg['standard_template_ready'])
            self.assertEqual(cfg['foam_segmentation'], 'fixed-threshold')
            sides = _inspect_layer_sides(image, cfg['foam_rois']['0'], cfg)
            for side in ('left', 'right'):
                self.assertEqual(np.count_nonzero(sides[side]['standard_mask']), 1600)
                self.assertAlmostEqual(sides[side]['offset_x_px'], 0)
        recipe.roi_config['leftFoamROI']['width'] = 50
        cfg = build_foam_inspection_config(recipe)
        sides = _inspect_layer_sides(image, cfg['foam_rois']['0'], cfg)
        self.assertEqual(np.count_nonzero(sides['left']['standard_mask']), 2000)

    def test_missing_roi_is_not_a_ready_standard(self):
        recipe = self.recipe()
        del recipe.roi_config['rightFoamROI']
        self.assertFalse(get_foam_standard_template_status(recipe)['ready'])
        with self.assertRaises(ValueError):
            build_foam_inspection_config(recipe)


class GrayTemplateIntegrationTests(SimpleTestCase):
    def test_teach_reload_inspect_and_readonly_replay(self):
        import io
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from django.test import override_settings
        from django.core.management import call_command
        from .algorithms.standard_mask_manager import StandardMaskManager
        from .algorithms.foam_inspector import FoamInspector

        image = np.full((180, 320, 3), 20, np.uint8)
        rois = {'layerSearchROI': {'x1r': 0, 'y1r': 0, 'x2r': 1, 'y2r': 1}}
        for side, x in (('left', 40), ('right', 200)):
            image[50:130, x:x+70] = 90
            # ROI is now the expected foam shape, rather than a loose search box.
            rois[side + 'FoamROI'] = {'x': x, 'y': 50, 'width': 70, 'height': 80}
        limits = dict(min_area_ratio=.8, max_area_ratio=1.25,
                      max_missing_ratio=.2, max_excess_ratio=.25)
        recipe = VisionRecipe(pk=42, pos=0, image_width=320, image_height=180,
                              roi_config=rois, recipe_type='FOAM_2D',
                              algorithm_config={'material_type': 'gray', 'foam_segmentation': 'gray-graphcut-v3'},
                              threshold_config=dict(limits, decision_mode='separated-v2'))
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            manager = StandardMaskManager(Path(directory) / 'standard_masks')
            template = manager.create_set_from_sample(image, recipe, 'integration',
                                                       build_foam_inspection_config(recipe))
            recipe.standard_template_config = template
            self.assertEqual(template['material_type'], 'gray')
            self.assertEqual(template['foam_segmentation'], 'gray-graphcut-v3')
            cfg = build_foam_inspection_config(recipe)
            self.assertTrue(cfg['standard_template_ready'])
            result = FoamInspector(simulate=False).inspect(image=image, inspection_config=cfg)
            self.assertTrue(result['is_passed'])
            self.assertEqual(result['result_data']['inspection_status'], 'PASS')
            self.assertEqual(result['result_data']['effective_config']['decision_mode'], 'separated-v2')
            json.dumps(result['result_data'], allow_nan=False)
            root = Path(directory)
            source = root / template['source_image_path']
            missing = root / 'missing.png'
            cv2.imwrite(str(missing), np.full_like(image, 20))
            limit_file = root / 'limits.json'
            limit_file.write_text(json.dumps(limits), encoding='utf-8')
            output = root / 'report.json'
            with patch('apps.vision.management.commands.replay_foam_quality.VisionRecipe.objects.get',
                       return_value=recipe):
                call_command('replay_foam_quality', recipe=42, images=[str(source), str(missing)],
                             limits=str(limit_file), output=str(output), stdout=io.StringIO())
            report = json.loads(output.read_text(encoding='utf-8'))
            self.assertTrue(report['images'][0]['trial']['is_passed'])
            self.assertFalse(report['images'][1]['trial']['is_passed'])
            self.assertFalse(report['images'][1]['trial']['is_complete'])
            self.assertEqual(report['segmentation'], 'gray-graphcut-v3')

    def test_separated_mode_cannot_fall_back_to_untemplated_detector(self):
        from .algorithms.foam_inspector import FoamInspector, StandardMaskConfigurationError
        cfg = dict(decision_mode='separated-v2', min_area_ratio=.8,
                   max_area_ratio=1.25, max_missing_ratio=.2, max_excess_ratio=.25)
        with self.assertRaises(StandardMaskConfigurationError):
            FoamInspector(simulate=False).inspect(image=np.zeros((100, 100, 3), np.uint8),
                                                  inspection_config=cfg)
