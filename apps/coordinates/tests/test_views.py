from django.test import TestCase


class CoordinatePageTests(TestCase):
    def test_coordinate_page_is_top_level_peer_after_vision(self):
        response = self.client.get('/coordinates/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '坐标模块')
        html = response.content.decode('utf-8')
        self.assertIn('href="/coordinates/"', html)
        self.assertLess(html.index('href="/vision/tasks/"'), html.index('href="/coordinates/"'))

    def test_workbench_contains_complete_coordinate_controls(self):
        response = self.client.get('/coordinates/')

        for marker in (
            'id="coordinate-workbench"',
            'id="coordinate-layer"',
            'id="hand-eye-matrix"',
            'id="robot-pose-fields"',
            'id="theoretical-fields"',
            'id="roi-fields"',
            'id="preview-coordinate"',
            'id="save-coordinate"',
            'id="restore-coordinate"',
            'id="camera-cloud"',
            'id="base-cloud"',
            'id="roi-cloud"',
            'id="coordinate-results"',
        ):
            self.assertContains(response, marker)
        self.assertContains(response, 'href="/vision/hand-eye/"')
        self.assertContains(response, 'coordinates/workbench.css')
        self.assertContains(response, 'coordinates/workbench.js')
