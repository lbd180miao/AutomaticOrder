from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import cv2
import numpy as np
from django.test import TestCase, override_settings

from apps.production.models import Product, Rack, RackRecipe
from apps.workflow.models import StationCycle, WorkflowInstance

from .models import RackLayerMeasurement, RackMeasurementProfile
from .rack_measurement import (
    RackMeasurementService,
    analyze_rack_image,
    measure_rack_recipe,
)


def synthetic_rack_image():
    image = np.full((420, 720, 3), 28, dtype=np.uint8)
    # 4 个开口：开口高 60 px，层距 75 px；2 mm/px => 120 / 150 mm。
    for index in range(4):
        top = 45 + index * 75
        bottom = top + 60
        cv2.line(image, (70, top), (650, top), (235, 235, 235), 4)
        cv2.line(image, (70, bottom), (650, bottom), (235, 235, 235), 4)
    cv2.line(image, (70, 35), (70, 345), (170, 170, 170), 5)
    cv2.line(image, (650, 35), (650, 345), (170, 170, 170), 5)
    return image


class RackMeasurementAlgorithmTests(TestCase):
    def test_detects_layer_count_height_and_spacing(self):
        result = analyze_rack_image(
            synthetic_rack_image(),
            layer_count=4,
            expected_layer_height=120,
            expected_layer_spacing=150,
            mm_per_pixel=2,
            roi_x=50,
            roi_y=20,
            roi_width=620,
            roi_height=350,
            edge_threshold=0.12,
            min_peak_distance=6,
        )

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.detected_layer_count, 4)
        self.assertAlmostEqual(result.measured_layer_height, 120, delta=6)
        self.assertAlmostEqual(result.measured_layer_spacing, 150, delta=6)
        self.assertGreaterEqual(result.confidence, 0.65)


class RackMeasurementAutomaticCallableTests(TestCase):
    def setUp(self):
        self.recipe = RackRecipe.objects.create(
            recipe_code='RCP-2D-AUTO', name='2D 自动配方', rack_type='A',
            layer_count=4, layer_height=120, layer_spacing=150, tolerance_z=3,
        )
        self.rack = Rack.objects.create(
            rack_code='RACK-2D-AUTO', rack_type='A', current_recipe=self.recipe,
        )
        self.product = Product.objects.create(product_code='PRODUCT-2D-AUTO', rack=self.rack)
        self.cycle = StationCycle.objects.create(
            workflow=WorkflowInstance.objects.create(product=self.product),
        )
        self.profile = RackMeasurementProfile.objects.create(
            name='自动配置', camera_code='CAM-RACK-01',
            roi_x=50, roi_y=20, roi_width=620, roi_height=350,
            mm_per_pixel=2, edge_threshold=.12, min_peak_distance=6,
        )

    def test_plc_callable_uses_active_profile_and_persists_audit(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=Path(media_root)):
            with mock.patch.object(
                RackMeasurementService, 'capture',
                return_value=(synthetic_rack_image(), 'D:/capture/rack.bmp'),
            ):
                result = measure_rack_recipe(
                    product=self.product, rack=self.rack, recipe=self.recipe,
                )

        self.assertAlmostEqual(result['measured_layer_height'], 120, delta=6)
        record = RackLayerMeasurement.objects.get(source='PLC_AUTO')
        self.assertEqual(record.station_cycle, self.cycle)
        self.assertTrue(record.is_success)
        self.assertTrue(record.passed)
