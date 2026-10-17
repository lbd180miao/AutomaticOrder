from unittest.mock import patch
from django.test import SimpleTestCase, RequestFactory
from django.core.files.uploadedfile import SimpleUploadedFile
import numpy as np
from .views import api_foam_upload_inspect
from .models import VisionRecipe
from .recipe_utils import get_foam_standard_template_status


class FoamUploadTests(SimpleTestCase):
    def test_failure_status_score_and_timing_are_preserved(self):
        result = dict(position_index=0, is_present=True, is_aligned=False,
                      is_passed=False, score=.6, offset_x_px=100, offset_y_px=0,
                      coverage_ratio=.8, defect_type='MISALIGNED', result_data={})
        with patch('apps.vision.views._decode_uploaded_image', return_value=np.zeros((10, 10, 3), np.uint8)), \
             patch('apps.vision.algorithms.foam_inspector.FoamInspector.inspect', return_value=result), \
             patch('apps.vision.views.VisionTask.objects.create') as task, \
             patch('apps.vision.views.FoamInspectionResult.objects.create') as record, \
             patch('apps.vision.views.foam_archive.archive'), \
             patch('apps.vision.views._result_payload', return_value={}):
            request = RequestFactory().post('/', {'use_recipe': 'false',
                'image': SimpleUploadedFile('sample.png', b'placeholder')})
            response = api_foam_upload_inspect(request)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(task.call_args.kwargs['status'], 'FAILED')
            self.assertEqual(record.call_args.kwargs['score'], .6)
            timing = record.call_args.kwargs['result_data']['timings_ms']
            self.assertGreaterEqual(timing['total'], timing['image_decode'])
            self.assertIn('algorithm_and_archive', timing)

    def test_changed_segmentation_requires_reteaching(self):
        recipe = VisionRecipe(algorithm_config={'foam_segmentation': 'shadow-graphcut-fast-v2'},
            standard_template_config={'foam_segmentation': 'shadow-graphcut-v1'})
        status = get_foam_standard_template_status(recipe)
        self.assertFalse(status['ready'])
        self.assertIn('分割算法', status['reason'])
