from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.core.constants import MesAction
from apps.mes.models import MesRecord


class RunMesRetryCommandTests(TestCase):
    @patch('apps.mes.management.commands.run_mes_retry.MesService.retry_record')
    def test_command_retries_failed_snapshot(self, retry_record):
        failed = MesRecord.objects.create(
            action=MesAction.UPLOAD_BOXING_RESULT,
            request_payload={'box': 'B-1'},
            success=False,
            error_message='timeout',
        )
        retry_record.return_value = {'success': True}
        output = StringIO()

        call_command('run_mes_retry', stdout=output)

        retry_record.assert_called_once_with(failed.pk)
        self.assertIn('成功 1 条', output.getvalue())

    @patch('apps.mes.management.commands.run_mes_retry.MesService.retry_record')
    def test_command_skips_failure_already_covered_by_later_success(self, retry_record):
        payload = {'box': 'B-RESOLVED'}
        MesRecord.objects.create(
            action=MesAction.UPLOAD_BOXING_RESULT,
            request_payload=payload,
            success=False,
            error_message='timeout',
        )
        MesRecord.objects.create(
            action=MesAction.UPLOAD_BOXING_RESULT,
            request_payload=payload,
            success=True,
        )

        call_command('run_mes_retry', stdout=StringIO())

        retry_record.assert_not_called()
