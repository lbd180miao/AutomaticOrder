from django.test import TestCase
from django.urls import reverse

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
        self.assertEqual(alarm.error_code, 'VISION_ERROR')

    def test_repeated_open_alarm_is_aggregated(self):
        first = self.service.create(source=AlarmSource.VISION, message='泡棉检测不合格')
        repeated = self.service.create(source=AlarmSource.VISION, message='泡棉检测不合格')

        self.assertEqual(first.pk, repeated.pk)
        self.assertEqual(repeated.occurrence_count, 2)
        self.assertEqual(Alarm.objects.count(), 1)

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
        self.assertEqual(alarm.actions.count(), 2)

    def test_open_alarms_excludes_closed(self):
        a = self.service.create(source=AlarmSource.SCANNER, message='扫码失败')
        self.service.close(a.id)
        self.assertFalse(self.service.open_alarms().exists())


class AlarmDetailViewTests(TestCase):
    def setUp(self):
        self.alarm = AlarmService().create(
            source=AlarmSource.DEVICE,
            message='PLC 通讯中断',
            lock_workstation=True,
        )

    def test_detail_displays_alarm_and_actions(self):
        response = self.client.get(reverse('alarms:alarm_detail', args=[self.alarm.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.alarm.alarm_code)
        self.assertContains(response, 'PLC 通讯中断')
        self.assertContains(response, '确认报警并开始处置')

    def test_acknowledge_from_detail_saves_note_and_returns_to_detail(self):
        response = self.client.post(
            reverse('alarms:acknowledge', args=[self.alarm.pk]),
            {'operator_note': '已通知电气检查', 'return_to': 'detail'},
        )
        self.assertRedirects(response, reverse('alarms:alarm_detail', args=[self.alarm.pk]))
        self.alarm.refresh_from_db()
        self.assertEqual(self.alarm.status, AlarmStatus.ACKNOWLEDGED)
        self.assertEqual(self.alarm.operator_note, '已通知电气检查')

    def test_close_from_detail_unlocks_and_saves_note(self):
        AlarmService().acknowledge(self.alarm.pk, operator_note='开始检查')
        response = self.client.post(
            reverse('alarms:close', args=[self.alarm.pk]),
            {'operator_note': '通讯恢复，关闭报警', 'return_to': 'detail'},
        )
        self.assertRedirects(response, reverse('alarms:alarm_detail', args=[self.alarm.pk]))
        self.alarm.refresh_from_db()
        self.assertEqual(self.alarm.status, AlarmStatus.CLOSED)
        self.assertFalse(self.alarm.locked_workstation)
        self.assertIn('通讯恢复', self.alarm.operator_note)

    def test_close_requires_acknowledgement(self):
        response = self.client.post(
            reverse('alarms:close', args=[self.alarm.pk]),
            {'operator_note': '试图直接关闭', 'return_to': 'detail'},
        )
        self.assertRedirects(response, reverse('alarms:alarm_detail', args=[self.alarm.pk]))
        self.alarm.refresh_from_db()
        self.assertEqual(self.alarm.status, AlarmStatus.OPEN)

    def test_closing_one_alarm_keeps_other_lock_active(self):
        other = AlarmService().create(
            source=AlarmSource.VISION,
            message='泡棉检测不合格',
            lock_workstation=True,
        )
        AlarmService().acknowledge(self.alarm.pk, operator_note='通讯已检查')
        response = self.client.post(
            reverse('alarms:close', args=[self.alarm.pk]),
            {'operator_note': 'PLC 通讯已恢复', 'return_to': 'detail'},
        )

        self.assertRedirects(response, reverse('alarms:alarm_detail', args=[self.alarm.pk]))
        self.alarm.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.alarm.status, AlarmStatus.CLOSED)
        self.assertTrue(other.locked_workstation)
        self.assertNotEqual(other.status, AlarmStatus.CLOSED)

    def test_list_is_recovery_workbench(self):
        response = self.client.get(reverse('alarms:alarm_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '报警恢复工作台')
        self.assertContains(response, '工位已锁定')
        self.assertContains(response, '引导式处置')
        self.assertContains(response, 'DEVICE_COMMUNICATION_FAILED')
