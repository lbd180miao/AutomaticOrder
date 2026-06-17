from django.test import TestCase

from apps.core.constants import WorkflowState as W
from apps.core.exceptions import WorkflowTransitionError
from apps.production.models import Product
from apps.workflow.models import WorkflowEvent
from apps.workflow.services import WorkflowService
from apps.workflow.state_machine import WorkflowStateMachine


class StateMachineTests(TestCase):
    def setUp(self):
        self.sm = WorkflowStateMachine()

    def test_legal_transition(self):
        self.assertTrue(self.sm.can_transition(W.CREATED, W.INJECTION_PICKED))

    def test_illegal_transition(self):
        self.assertFalse(self.sm.can_transition(W.CREATED, W.COMPLETED))

    def test_terminal_cannot_transition(self):
        self.assertFalse(self.sm.can_transition(W.COMPLETED, W.BOXING))

    def test_universal_lock_target(self):
        self.assertTrue(self.sm.can_transition(W.BOXING, W.LOCKED))

    def test_next_state_skips_exception_targets(self):
        # BOXING 的唯一正常下一步是 FOAM_PICKING（不应是 LOCKED/FAILED）。
        self.assertEqual(self.sm.next_state(W.BOXING), W.FOAM_PICKING)


class WorkflowServiceTests(TestCase):
    def setUp(self):
        self.service = WorkflowService()

    def test_start_creates_instance_and_event(self):
        wf = self.service.start('P-TEST-1')
        self.assertEqual(wf.current_state, W.CREATED)
        self.assertTrue(WorkflowEvent.objects.filter(workflow=wf).exists())

    def test_full_flow_to_completed(self):
        wf = self.service.start('P-TEST-FULL')
        guard = 0
        while wf.current_state not in (W.COMPLETED, W.LOCKED, W.FAILED) and guard < 40:
            self.service.advance(wf)
            wf.refresh_from_db()
            guard += 1
        self.assertEqual(wf.current_state, W.COMPLETED)
        self.assertIsNotNone(wf.finished_at)
        product = Product.objects.get(product_code='P-TEST-FULL')
        self.assertEqual(product.current_state, W.COMPLETED)

    def test_illegal_transition_raises(self):
        wf = self.service.start('P-TEST-ILLEGAL')
        with self.assertRaises(WorkflowTransitionError):
            self.service._transition(wf, W.COMPLETED, 'SYSTEM')


class WorkflowFailureTests(TestCase):
    def _locked_service(self):
        from apps.devices.adapters.simulated import SimulatedDeviceAdapter
        from apps.devices.services import DeviceService

        adapter = SimulatedDeviceAdapter(fail_product_scan=True)
        return WorkflowService(device_service=DeviceService(adapter=adapter))

    def test_scan_failure_locks_and_alarms(self):
        from apps.alarms.models import Alarm

        service = self._locked_service()
        wf = service.start('P-TEST-FAIL')
        guard = 0
        while wf.current_state not in (W.LOCKED, W.COMPLETED, W.FAILED) and guard < 20:
            service.advance(wf)
            wf.refresh_from_db()
            guard += 1
        self.assertEqual(wf.current_state, W.LOCKED)
        self.assertTrue(wf.is_locked)
        self.assertTrue(Alarm.objects.filter(workflow=wf).exists())

    def test_unlock_resume(self):
        service = self._locked_service()
        wf = service.start('P-TEST-UNLOCK')
        guard = 0
        while wf.current_state != W.LOCKED and guard < 20:
            service.advance(wf)
            wf.refresh_from_db()
            guard += 1
        self.assertEqual(wf.current_state, W.LOCKED)
        service.unlock(wf, resume=True, operator_note='已处理')
        wf.refresh_from_db()
        self.assertFalse(wf.is_locked)
        self.assertNotEqual(wf.current_state, W.LOCKED)
