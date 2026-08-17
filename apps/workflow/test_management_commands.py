from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

class RunWorkflowWorkerCommandTests(TestCase):
    @patch('apps.workflow.management.commands.run_workflow_worker.StationWorkflowService')
    def test_once_polls_db100_station(self, service_class):
        cycle = service_class.return_value.poll_once.return_value = (
            type('Cycle', (), {
                'pk': 7,
                'get_phase_display': lambda self: '等待产品条码',
            })(),
            False,
        )
        output = StringIO()

        call_command('run_workflow_worker', '--once', stdout=output)

        service_class.return_value.poll_once.assert_called_once_with()
        self.assertIn('等待产品条码', output.getvalue())
