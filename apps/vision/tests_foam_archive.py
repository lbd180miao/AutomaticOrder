import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from django.test import SimpleTestCase, RequestFactory, override_settings
from django.utils import timezone
from . import foam_archive
from .models import FoamInspectionResult
from .views import api_foam_save_images, api_foam_record_image


class FoamArchiveTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.addCleanup(self.temp.cleanup)
        self.settings_override = override_settings(BASE_DIR=Path(self.temp.name))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def archive(self, result_id):
        image = np.zeros((12, 16, 3), dtype=np.uint8)
        raw, _, _ = foam_archive.save_image(image, 'raw')
        annotated, _, _ = foam_archive.save_image(image, 'result')
        result = FoamInspectionResult(id=result_id, vision_task_id=result_id,
                                      created_at=timezone.now(), result_data={'sides': {}})
        foam_archive.archive(result, {'original_image': raw, 'result_image': annotated})

    def test_display_is_bounded_jpeg_and_original_pixels_are_lossless(self):
        rng = np.random.default_rng(42)
        image = rng.integers(0, 256, (1200, 1800, 3), dtype=np.uint8)
        original, width, height = foam_archive.save_image(image, 'raw')
        display, _, _ = foam_archive.save_image(image, 'result', extension='jpg')
        self.assertEqual((width, height), (1800, 1200))
        self.assertTrue(display.startswith(b'\xff\xd8'))
        decoded = cv2.imdecode(np.frombuffer(original, dtype=np.uint8), cv2.IMREAD_COLOR)
        np.testing.assert_array_equal(decoded, image)
        shown = cv2.imdecode(np.frombuffer(display, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertLessEqual(max(shown.shape[:2]), 1600)
        result = FoamInspectionResult(id=101, vision_task_id=101, created_at=timezone.now())
        foam_archive.archive(result, {'original_image': original, 'result_image': display})
        response = api_foam_record_image(RequestFactory().get('/'), 101, 'result')
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        foam_archive.save_images(101)
        saved = cv2.imread(str(foam_archive.image_path(101, 'original')))
        np.testing.assert_array_equal(saved, image)

    def test_inspection_never_reuses_preview_frame(self):
        from .views import api_foam_capture_inspect
        request = RequestFactory().post('/', json.dumps({
            'preview_capture_token': 'old-preview', 'position_index': 0,
        }), content_type='application/json')
        with patch('apps.vision.views.VisionService') as service, \
             patch('apps.vision.views._result_payload', return_value={}):
            response = api_foam_capture_inspect(request)
        self.assertEqual(response.status_code, 200)
        kwargs = service.return_value.inspect_foam.call_args.kwargs
        self.assertTrue(kwargs['use_camera'])
        self.assertNotIn('captured_image_path', kwargs)

    def test_quality_statistics_match_full_resolution_numpy_calculation(self):
        from .algorithms.foam_inspector import _analyze_image_quality
        image = np.random.default_rng(73).integers(0, 256, (360, 480, 3), dtype=np.uint8)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        quality = _analyze_image_quality(image, (0, 0, 480, 360))
        self.assertAlmostEqual(quality['mean_brightness'], round(float(np.mean(gray)), 1), places=2)
        self.assertAlmostEqual(quality['std_brightness'], round(float(np.std(gray)), 1), places=2)
        self.assertAlmostEqual(quality['sharpness_score'], round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1), places=2)
        self.assertAlmostEqual(quality['noise_level'], round(float(np.std(cv2.GaussianBlur(gray, (5, 5), 0) - gray)), 2), places=2)

    def test_data_only_archive_and_manual_save(self):
        self.archive(1)
        root = foam_archive.root()
        self.assertTrue((root / '1.json').exists())
        self.assertFalse(list(root.glob('*.png')))
        with patch('apps.vision.views.FoamInspectionResult.objects') as manager:
            manager.filter.return_value.exists.return_value = True
            response = api_foam_save_images(RequestFactory().post('/'), 1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(list(root.glob('*.png'))), 1)
        self.assertTrue(json.loads((root / '1.json').read_text())['images_saved'])
        response = api_foam_record_image(RequestFactory().get('/'), 1, 'original')
        self.assertEqual(response.status_code, 200)
        response.close()
        foam_archive._latest_images.pop('result', None)  # Saving only needs the raw image.
        foam_archive.save_images(1)  # Repeated clicks are idempotent.
        self.assertEqual([p.name for p in root.glob('*.png')], ['1_original.png'])

    def test_cache_is_bounded_but_records_and_saved_images_survive(self):
        self.archive(1)
        foam_archive.save_images(1)
        for result_id in range(2, 20):
            self.archive(result_id)
        root = foam_archive.root()
        self.assertFalse((root / '.cache').exists())
        self.assertFalse(foam_archive.has_image(2, 'original'))
        self.assertTrue(foam_archive.has_image(19, 'original'))
        self.assertEqual(len(list(root.glob('*.json'))), 19)
        self.assertTrue((root / '1_original.png').exists())
        with self.assertRaisesMessage(ValueError, '缓存已过期'):
            foam_archive.save_images(2)
        with self.assertRaises(ValueError):
            foam_archive.image_path(1, '../invalid')


from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
import cv2
from .models import VisionImage


class FoamUploadArchiveTests(TestCase):
    def test_upload_keeps_data_without_permanent_images(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
            with override_settings(BASE_DIR=Path(directory), MIDDLEWARE=[]):
                image = np.zeros((100, 160, 3), dtype=np.uint8)
                ok, encoded = cv2.imencode('.png', image)
                self.assertTrue(ok)
                response = self.client.post('/vision/api/foam/upload-inspect/', {
                    'image': SimpleUploadedFile('sample.png', encoded.tobytes(), content_type='image/png'),
                    'use_recipe': 'false',
                })
                self.assertEqual(response.status_code, 200, response.content)
                body = response.json()
                self.assertTrue(body['success'], body)
                result_id = body['result']['result_id']
                self.assertTrue(FoamInspectionResult.objects.filter(pk=result_id).exists())
                self.assertFalse(VisionImage.objects.exists())
                self.assertTrue((foam_archive.root() / f'{result_id}.json').is_file())
                self.assertFalse(list(foam_archive.root().glob('*.png')))
                response = self.client.post(f'/vision/api/foam/records/{result_id}/save-images/')
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(len(list(foam_archive.root().glob('*.png'))), 1)
