from django.test import TestCase


class CoordinatePageTests(TestCase):
    def test_coordinate_page_is_top_level_peer_after_vision(self):
        response = self.client.get('/coordinates/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '坐标模块')
        html = response.content.decode('utf-8')
        self.assertIn('href="/coordinates/"', html)
        self.assertLess(html.index('href="/vision/tasks/"'), html.index('href="/coordinates/"'))

