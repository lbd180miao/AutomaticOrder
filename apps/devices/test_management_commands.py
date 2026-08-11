from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase


class RunDevicePollingCommandTests(TestCase):
    @patch('apps.devices.management.commands.run_device_polling.DeviceService.refresh_all_status')
    def test_once_refreshes_status_and_exits(self, refresh_all_status):
        output = StringIO()
        call_command('run_device_polling', '--once', stdout=output)
        refresh_all_status.assert_called_once_with()
        self.assertIn('设备状态已刷新', output.getvalue())
