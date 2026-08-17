"""Run a byte-accurate DB100 cycle without PLC/camera/MES hardware."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings
from django.utils import timezone

from apps.devices.adapters.plc import MemoryPLCTransport, PLCAdapter
from apps.mes.client import SimulatedMesClient
from apps.mes.services import MesService
from apps.workflow.models import StationPhase
from apps.workflow.station_service import ExistingVisionGateway, StationWorkflowService


class Command(BaseCommand):
    help = '使用内存 PLC 和模拟 MES/视觉跑通一次完整 DB100 装箱周期'

    def add_arguments(self, parser):
        parser.add_argument('--product-code', default='')
        parser.add_argument('--rack-code', default='')
        parser.add_argument('--quantity', type=int, default=2)

    def handle(self, *args, **options):
        quantity = options['quantity']
        if quantity <= 0 or quantity > 1000:
            raise CommandError('--quantity 必须在 1..1000')
        stamp = timezone.now().strftime('%m%d%H%M%S')
        product_code = options['product_code'] or f'SIM-P-{stamp}'
        rack_code = options['rack_code'] or f'SIM-R-{stamp}'

        plc = PLCAdapter(transport=MemoryPLCTransport())
        plc.connect()
        config = {
            **getattr(settings, 'AUTOMATIC_ORDER', {}),
            'USE_SIMULATED_DEVICES': True,
        }
        with override_settings(AUTOMATIC_ORDER=config):
            service = StationWorkflowService(
                plc=plc,
                mes_service=MesService(client=SimulatedMesClient(recipe_overrides={
                    'total_quantity': quantity,
                    'quantity_per_layer': quantity,
                })),
                vision_gateway=ExistingVisionGateway(),
            )
            service.poll_once()
            plc.write_point('product_barcode', product_code)
            self._pulse(service, plc, 'mark_trigger')
            plc.write_point('rack_barcode', rack_code)
            self._pulse(service, plc, 'rack_trigger')
            self._pulse(service, plc, 'position_trigger')
            self._pulse(service, plc, 'recipe_verify_trigger')
            for loaded in range(1, quantity + 1):
                self._pulse(service, plc, 'foam_trigger')
                plc.write_point('boxing_trigger', True)
                service.poll_once()
                plc.write_point('loaded_quantity', loaded)
                plc.write_point('boxing_trigger', False)
                cycle, _ = service.poll_once()
                self.stdout.write(f'已装 {loaded}/{quantity} · {cycle.get_phase_display()}')

        if cycle.phase != StationPhase.COMPLETED:
            raise CommandError(f'联调未完成，最终阶段: {cycle.phase}')
        self.stdout.write(self.style.SUCCESS(
            f'DB100 全链路联调成功：{product_code} → {rack_code}，数量 {quantity}',
        ))

    @staticmethod
    def _pulse(service, plc, point):
        plc.write_point(point, True)
        service.poll_once()
        plc.write_point(point, False)
        service.poll_once()

