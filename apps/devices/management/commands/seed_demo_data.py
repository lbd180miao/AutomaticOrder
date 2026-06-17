"""生成更丰富的演示数据，让各页面有内容可看。

会用真实的 WorkflowService 跑出若干条不同进度的流程，从而自然产生：
产品、流程事件、视觉结果、MES 记录、设备信号、报警等。

用法：
  python manage.py seed_demo_data            # 追加演示数据
  python manage.py seed_demo_data --reset    # 先清空演示数据再生成
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.core.constants import WorkflowState as W
from apps.devices.adapters.simulated import SimulatedDeviceAdapter
from apps.devices.services import DeviceService
from apps.production.models import ProductionBatch, Product
from apps.workflow.services import WorkflowService


def _make_service(**adapter_kwargs):
    adapter = SimulatedDeviceAdapter(**adapter_kwargs)
    return WorkflowService(device_service=DeviceService(adapter=adapter))


class Command(BaseCommand):
    help = '生成丰富的演示数据（多条不同进度的流程、视觉/MES/报警记录）'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='先清空演示数据')

    def handle(self, *args, **options):
        if options['reset']:
            self._reset()

        # 确保基础数据（设备、配方、批次）存在。
        call_command('seed_demo')
        batch = ProductionBatch.objects.filter(batch_no='BATCH-DEMO-001').first()

        # 1) 两条完整跑完的流程（COMPLETED）。
        for i in range(1, 3):
            self._run_to_end(f'P-DEMO-DONE-{i:03d}', batch)

        # 2) 三条停在不同阶段的进行中流程。
        self._run_steps(f'P-DEMO-WIP-001', batch, 3)   # 阶段一中段
        self._run_steps(f'P-DEMO-WIP-002', batch, 8)   # 阶段二
        self._run_steps(f'P-DEMO-WIP-003', batch, 12)  # 阶段三

        # 3) 一条扫码失败 -> 锁定并产生报警的流程。
        self._run_until_locked('P-DEMO-LOCK-001', batch)

        # 4) 一条泡棉检测不合格的流程（锁定 + 视觉不合格记录）。
        self._run_foam_fail('P-DEMO-FOAM-001', batch)

        self.stdout.write(self.style.SUCCESS('丰富演示数据生成完成'))
        self._summary()

    # ---------- helpers ----------
    def _run_to_end(self, code, batch):
        service = _make_service()
        wf = service.start(code, batch=batch)
        self._advance_until(service, wf, {W.COMPLETED, W.LOCKED, W.FAILED})

    def _run_steps(self, code, batch, steps):
        service = _make_service()
        wf = service.start(code, batch=batch)
        for _ in range(steps):
            wf.refresh_from_db()
            if wf.current_state in (W.COMPLETED, W.LOCKED, W.FAILED):
                break
            try:
                service.advance(wf)
            except Exception:  # noqa: BLE001
                break

    def _run_until_locked(self, code, batch):
        service = _make_service(fail_product_scan=True)
        wf = service.start(code, batch=batch)
        self._advance_until(service, wf, {W.LOCKED, W.COMPLETED, W.FAILED})

    def _run_foam_fail(self, code, batch):
        # 用自定义视觉服务让泡棉检测返回不合格。
        from apps.vision.services import VisionService

        class _FailFoamVision(VisionService):
            def inspect_foam(self, product, rack, position_index=0, simulated_pass=True):
                return super().inspect_foam(product, rack, position_index, simulated_pass=False)

        adapter = SimulatedDeviceAdapter()
        service = WorkflowService(
            device_service=DeviceService(adapter=adapter),
            vision_service=_FailFoamVision(),
        )
        wf = service.start(code, batch=batch)
        self._advance_until(service, wf, {W.LOCKED, W.COMPLETED, W.FAILED})

    def _advance_until(self, service, wf, stop_states, guard=40):
        n = 0
        while n < guard:
            wf.refresh_from_db()
            if wf.current_state in stop_states:
                break
            try:
                service.advance(wf)
            except Exception:  # noqa: BLE001
                break
            n += 1

    def _reset(self):
        from apps.workflow.models import WorkflowInstance, WorkflowEvent
        from apps.vision.models import VisionTask, RackLocationResult, FoamInspectionResult
        from apps.mes.models import MesRecord
        from apps.alarms.models import Alarm
        from apps.devices.models import DeviceSignalRecord

        Alarm.objects.all().delete()
        FoamInspectionResult.objects.all().delete()
        RackLocationResult.objects.all().delete()
        VisionTask.objects.all().delete()
        MesRecord.objects.all().delete()
        WorkflowEvent.objects.all().delete()
        WorkflowInstance.objects.all().delete()
        DeviceSignalRecord.objects.all().delete()
        Product.objects.all().delete()
        self.stdout.write(self.style.WARNING('已清空演示流程数据'))

    def _summary(self):
        from apps.workflow.models import WorkflowInstance
        from apps.vision.models import RackLocationResult, FoamInspectionResult
        from apps.mes.models import MesRecord
        from apps.alarms.models import Alarm

        self.stdout.write(f'  产品: {Product.objects.count()}')
        self.stdout.write(f'  流程实例: {WorkflowInstance.objects.count()}')
        self.stdout.write(f'  料架定位结果: {RackLocationResult.objects.count()}')
        self.stdout.write(f'  泡棉检测结果: {FoamInspectionResult.objects.count()}')
        self.stdout.write(f'  MES 记录: {MesRecord.objects.count()}')
        self.stdout.write(f'  报警: {Alarm.objects.count()}')
