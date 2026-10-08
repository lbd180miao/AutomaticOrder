import json
import tempfile
from pathlib import Path

import numpy as np
from django.test import SimpleTestCase

from .pointcloud_units import load_pointcloud_mm, to_millimeters
from .rack_location import _measure_layer_spacing_line


class PointcloudUnitTests(SimpleTestCase):
    def test_meter_and_millimeter_clouds_measure_the_same_endpoint_distance(self):
        cloud = np.zeros((40, 80, 3), dtype=float)
        cloud[:, :40] = [0, 0, 1000]
        cloud[:, 40:] = [600, 0, 1000]
        line = dict(x1=20, y1=20, x2=60, y2=20, sample_radius=8)
        for unit, data in [('mm', cloud), ('m', cloud / 1000)]:
            distance, details = _measure_layer_spacing_line(to_millimeters(data, unit), line)
            self.assertAlmostEqual(distance, 600)
            self.assertEqual(details['endpoints'][0]['point_mm'], [0, 0, 1000])

    def test_marker_is_repeatable_and_does_not_modify_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cloud.npy'
            source = np.array([[[0.1, 0.2, 1.0]]])
            np.save(path, source)
            path.with_suffix('.units.json').write_text(json.dumps({'unit': 'm'}))
            for _ in range(2):
                np.testing.assert_allclose(load_pointcloud_mm(path), source * 1000)
            np.testing.assert_array_equal(np.load(path), source)

    def test_small_millimeter_coordinates_are_not_guessed_as_meters(self):
        source = np.array([[[0.1, 0.2, 1.0]]])
        self.assertIs(to_millimeters(source, 'mm'), source)
        with self.assertRaises(ValueError):
            to_millimeters(source, 'unknown')
