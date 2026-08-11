from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.core.constants import Stage, WorkflowState
from apps.production.models import Product
from apps.workflow.models import WorkflowInstance


class RunWorkflowWorkerCommandTests(TestCase):
    @patch('apps.workflow.management.commands.run_workflow_worker.WorkflowService')
    def test_once_advances_runnable_workflow(self, service_class):
        product = Product.objects.create(product_code='WORKER-CMD-PRODUCT')
        workflow = WorkflowInstance.objects.create(
            product=product,
            current_state=WorkflowState.CREATED,
            current_stage=Stage.STAGE_ONE,
        )
        output = StringIO()

        call_command('run_workflow_worker', '--once', stdout=output)

        service_class.return_value.advance.assert_called_once()
        called_workflow = service_class.return_value.advance.call_args.args[0]
        self.assertEqual(called_workflow.pk, workflow.pk)
        self.assertIn('成功推进 1 条', output.getvalue())
