"""CompensationCalculator 单元测试。Requirements: 26.1, 26.2"""

import unittest

from apps.vision.rack_3d.calculators import CompensationCalculator


class TestCalculator(unittest.TestCase):
    def setUp(self):
        self.calc = CompensationCalculator()

    def test_actual_values_packaging(self):
        out = self.calc.calculate_actual_values(1, 2, 3, 0.9, 0.8, 0.7)
        self.assertEqual(out['actual_x'], 1.0)
        self.assertEqual(out['actual_z'], 3.0)
        self.assertEqual(out['confidence_y'], 0.8)

    def test_offsets_positive_negative_zero(self):
        """Property 5: offset = actual - standard。"""
        self.assertAlmostEqual(
            self.calc.calculate_offsets(105, 500, 800, 100, 500, 805)['offset_x'], 5.0)
        self.assertAlmostEqual(
            self.calc.calculate_offsets(105, 500, 800, 100, 500, 805)['offset_z'], -5.0)
        self.assertAlmostEqual(
            self.calc.calculate_offsets(100, 500, 805, 100, 500, 805)['offset_y'], 0.0)

    def test_offset_precision_to_millimeter(self):
        out = self.calc.calculate_offsets(1000.123, 0, 0, 1000.000, 0, 0)
        self.assertAlmostEqual(out['offset_x'], 0.123, places=3)

    def test_compensation_equals_offset_by_default(self):
        out = self.calc.calculate_compensations(2.0, -3.0, 4.0)
        self.assertEqual(out['compensation_x'], 2.0)
        self.assertEqual(out['compensation_y'], -3.0)

    def test_compensation_negative_feedback(self):
        calc = CompensationCalculator(sign_convention=-1.0)
        out = calc.calculate_compensations(2.0, -3.0, 4.0)
        self.assertEqual(out['compensation_x'], -2.0)

    def test_validate_accepts_valid(self):
        ok, msg = self.calc.validate_result(1, 1, 1, 10, 10, 10, 0.9, 0.7)
        self.assertTrue(ok)
        self.assertIsNone(msg)

    def test_validate_rejects_excessive_offset(self):
        ok, msg = self.calc.validate_result(50, 1, 1, 10, 10, 10, 0.9, 0.7)
        self.assertFalse(ok)
        self.assertIn('超出', msg)

    def test_validate_rejects_low_confidence(self):
        ok, msg = self.calc.validate_result(1, 1, 1, 10, 10, 10, 0.5, 0.7)
        self.assertFalse(ok)
        self.assertIn('置信度', msg)

    def test_overall_confidence_is_min(self):
        self.assertEqual(self.calc.calculate_overall_confidence(0.9, 0.8, 0.95), 0.8)


if __name__ == '__main__':
    unittest.main()
