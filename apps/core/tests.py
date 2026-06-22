from django.test import TestCase
from django.urls import reverse


class PageAccessTests(TestCase):
    """所有主要页面应可访问（返回 200）。"""

    def test_dashboard(self):
        self.assertEqual(self.client.get(reverse('core:dashboard')).status_code, 200)

    def test_dashboard_links_to_vision_recipe_workbench(self):
        response = self.client.get(reverse('core:dashboard'))

        self.assertContains(response, '视觉配方模块')
        self.assertContains(response, reverse('vision:foam_inspector_interactive'))
        self.assertContains(response, '配方管理')

    def test_product_list(self):
        self.assertEqual(self.client.get(reverse('production:product_list')).status_code, 200)

    def test_rack_list(self):
        self.assertEqual(self.client.get(reverse('production:rack_list')).status_code, 200)

    def test_recipe_list(self):
        self.assertEqual(self.client.get(reverse('production:recipe_list')).status_code, 200)

    def test_workflow_current(self):
        self.assertEqual(self.client.get(reverse('workflow:current')).status_code, 200)

    def test_workflow_history(self):
        self.assertEqual(self.client.get(reverse('workflow:history')).status_code, 200)

    def test_devices_status(self):
        self.assertEqual(self.client.get(reverse('devices:status')).status_code, 200)

    def test_devices_signals(self):
        self.assertEqual(self.client.get(reverse('devices:signals')).status_code, 200)

    def test_vision_task_list(self):
        self.assertEqual(self.client.get(reverse('vision:task_list')).status_code, 200)

    def test_vision_rack_results(self):
        self.assertEqual(self.client.get(reverse('vision:rack_results')).status_code, 200)

    def test_vision_foam_results(self):
        self.assertEqual(self.client.get(reverse('vision:foam_results')).status_code, 200)

    def test_mes_records(self):
        self.assertEqual(self.client.get(reverse('mes:record_list')).status_code, 200)

    def test_alarms(self):
        self.assertEqual(self.client.get(reverse('alarms:alarm_list')).status_code, 200)

    def test_traceability_search(self):
        self.assertEqual(self.client.get(reverse('traceability:search')).status_code, 200)


class WorkflowPageActionTests(TestCase):
    def test_start_and_advance_via_views(self):
        # 新建流程。
        resp = self.client.post(reverse('workflow:start'), {'product_code': 'P-VIEW-1'})
        self.assertEqual(resp.status_code, 302)
        from apps.workflow.models import WorkflowInstance
        wf = WorkflowInstance.objects.get(product__product_code='P-VIEW-1')
        # 推进一步。
        resp = self.client.post(reverse('workflow:advance', args=[wf.pk]))
        self.assertEqual(resp.status_code, 302)
        wf.refresh_from_db()
        self.assertNotEqual(wf.current_state, 'CREATED')
