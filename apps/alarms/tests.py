from django.test import TestCase

from apps.alarms.models import Alarm
from apps.alarms.services import AlarmService
from apps.core.constants import AlarmLevel, AlarmSource, AlarmStatus


class AlarmServiceTests(TestCase):
    def setUp(self):
        self.service = AlarmService()

    def test_create_alarm(self):
        alarm = self.service.create(source=AlarmSource.VISION, message='视觉失败')
        self.assertEqual(alarm.status, AlarmStatus.OPEN)
        self.assertTrue(alarm.alarm_code)

    def test_critical_locks_workstation(self):
        alarm = self.service.create(
            source=AlarmSource.DEVICE, message='严重', level=AlarmLevel.CRITICAL,
        )
        self.assertTrue(alarm.locked_workstation)

    def test_acknowledge_then_close(self):
        alarm = self.service.create(source=AlarmSource.MES, message='上传失败',
                                    lock_workstation=True)
        self.service.acknowledge(alarm.id, operator_note='查看中')
        alarm.refresh_from_db()
        self.assertEqual(alarm.status, AlarmStatus.ACKNOWLEDGED)

        self.service.close(alarm.id, operator_note='已恢复')
        alarm.refresh_from_db()
        self.assertEqual(alarm.status, AlarmStatus.CLOSED)
        self.assertFalse(alarm.locked_workstation)

    def test_open_alarms_excludes_closed(self):
        a = self.service.create(source=AlarmSource.SCANNER, message='扫码失败')
        self.service.close(a.id)
        self.assertFalse(self.service.open_alarms().exists())
