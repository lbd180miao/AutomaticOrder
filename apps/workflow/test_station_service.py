from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.alarms.models import Alarm
from apps.devices.adapters.plc import MemoryPLCTransport, PLCAdapter
from apps.mes.client import SimulatedMesClient
from apps.mes.services import MesService
from apps.production.models import Rack, RackRecipe, RackRecipeVisionMapping
from apps.vision.models import RackLocationRecipe
from apps.workflow.models import StationCycle, StationPhase, WorkflowEvent
from apps.workflow.station_service import ExistingVisionGateway, StationWorkflowService


class FakeVisionGateway:
    def __init__(self, *, measured=(120.0, 150.0)):
        self.measured = measured
        self.position_calls = 0

    def calculate_position_delta_z(self, cycle):
        self.position_calls += 1
        return 30.0

    def measure_recipe(self, cycle):
        return self.measured


class ExistingVisionGatewayMappingTests(TestCase):
    @override_settings(AUTOMATIC_ORDER={
        'USE_SIMULATED_DEVICES': False,
        'VISION_POSITION_RECIPE_ID': None,
    })
    @patch('apps.vision.rack_3d.services.RackPositioningService.execute_positioning')
    def test_uses_current_layer_mapping_for_station_position(self, execute_positioning):
        master = RackRecipe.objects.create(
            recipe_code='MASTER-POSITION', name='主配方', rack_type='RACK-A',
            station_position_count=2, layer_count=3, quantity_per_layer=5,
            total_quantity=15,
        )
        rack = Rack.objects.create(
            rack_code='RACK-POSITION', rack_type='RACK-A',
            position_side='2', current_recipe=master,
        )
        vision_recipe = RackLocationRecipe.objects.create(
            recipe_name='P2-L2', rack_type='RACK-A', position_no=2, layer_no=2,
            roi_config={
                'target_roi': {'x': 1},
                'local_template_rois': {
                    'plane1': {'x': 1}, 'plane2': {'x': 2}, 'plane3': {'x': 3},
                },
            },
            local_template_std={'origin': [0, 0, 0]},
            hand_eye_config={'matrix': 'identity'},
        )
        RackRecipeVisionMapping.objects.create(
            rack_recipe=master, station_position_no=2, layer_no=2,
            rack_location_recipe=vision_recipe,
        )
        cycle = StationCycle.objects.create(rack=rack, loaded_quantity=5)
        execute_positioning.return_value = {
            'is_success': True, 'compensation_z': 2.5,
        }

        delta_z = ExistingVisionGateway().calculate_position_delta_z(cycle)

        self.assertEqual(delta_z, 2.5)
        execute_positioning.assert_called_once_with(
            vision_recipe.id, 2, save=True,
        )

class StationWorkflowIntegrationTests(TestCase):
    def setUp(self):
        self.transport = MemoryPLCTransport()
        self.plc = PLCAdapter(transport=self.transport)
        self.plc.connect()
        self.vision = FakeVisionGateway()
        mes = MesService(client=SimulatedMesClient(recipe_overrides={
            'total_quantity': 1,
        }))
        self.service = StationWorkflowService(
            plc=self.plc, mes_service=mes, vision_gateway=self.vision,
        )

    def poll(self, expected):
        cycle, _changed = self.service.poll_once()
        cycle.refresh_from_db()
        self.assertEqual(cycle.phase, expected)
        return cycle

    def pulse(self, point, processing_phase, reset_phase):
        self.plc.write_point(point, True)
        cycle = self.poll(processing_phase)
        # Holding a trigger high must not execute the integration twice.
        self.poll(processing_phase)
        self.plc.write_point(point, False)
        self.poll(reset_phase)
        return cycle

    def test_complete_db100_chain(self):
        self.poll(StationPhase.WAIT_RACK)
        self.plc.write_point('rack_barcode', 'RK-DB100-01')
        self.pulse('rack_trigger', StationPhase.WAIT_RACK_RESET, StationPhase.WAIT_RECIPE_VERIFY)
        self.assertFalse(self.plc.read_point('rack_done'))

        self.pulse('recipe_verify_trigger', StationPhase.WAIT_RECIPE_RESET, StationPhase.WAIT_POSITION)
        self.assertFalse(self.plc.read_point('recipe_verify_done'))

        self.pulse('position_trigger', StationPhase.WAIT_POSITION_RESET, StationPhase.WAIT_PRODUCT)
        self.assertEqual(self.vision.position_calls, 1)
        self.assertAlmostEqual(self.plc.read_point('layer_delta_z'), 30.0)

        self.plc.write_point('product_barcode', 'P-DB100-001')
        self.pulse('mark_trigger', StationPhase.WAIT_MARK_RESET, StationPhase.WAIT_FOAM)
        self.assertFalse(self.plc.read_point('mark_read_done'))

        self.plc.write_point('foam_passed', True)
        self.pulse('foam_trigger', StationPhase.WAIT_FOAM_RESET, StationPhase.WAIT_BOXING)
        cycle = self.pulse('boxing_trigger', StationPhase.WAIT_BOXING_RESET, StationPhase.COMPLETED)

        self.assertEqual(cycle.loaded_quantity, 1)
        self.assertEqual(cycle.planned_quantity, 1)
        self.assertEqual(cycle.rack.rack_code, 'RK-DB100-01')
        self.assertTrue(WorkflowEvent.objects.filter(event_type='RACK_FULL').exists())
        self.assertFalse(self.plc.read_point('mes_upload_done'))

    def test_foam_failure_from_plc_locks_after_recording(self):
        self.poll(StationPhase.WAIT_RACK)
        self.plc.write_point('rack_barcode', 'RK-DB100-NG')
        self.pulse('rack_trigger', StationPhase.WAIT_RACK_RESET, StationPhase.WAIT_RECIPE_VERIFY)
        self.pulse('recipe_verify_trigger', StationPhase.WAIT_RECIPE_RESET, StationPhase.WAIT_POSITION)
        self.pulse('position_trigger', StationPhase.WAIT_POSITION_RESET, StationPhase.WAIT_PRODUCT)
        self.plc.write_point('product_barcode', 'P-DB100-NG')
        self.pulse('mark_trigger', StationPhase.WAIT_MARK_RESET, StationPhase.WAIT_FOAM)

        self.plc.write_point('foam_passed', False)
        self.plc.write_point('foam_trigger', True)
        cycle = self.poll(StationPhase.LOCKED)
        self.assertFalse(self.plc.read_point('foam_passed'))
        self.assertTrue(self.plc.read_point('foam_done'))
        self.assertTrue(self.plc.read_point('workstation_locked'))
        self.assertTrue(cycle.is_locked)
        self.assertTrue(Alarm.objects.filter(workflow=cycle.workflow, locked_workstation=True).exists())

        self.plc.write_point('foam_trigger', False)
        self.service.unlock(cycle, operator_note='复检')
        cycle.refresh_from_db()
        self.assertEqual(cycle.phase, StationPhase.WAIT_FOAM_RESET)
        self.assertFalse(self.plc.read_point('workstation_locked'))
        self.poll(StationPhase.WAIT_FOAM)
        self.plc.write_point('foam_passed', True)
        self.plc.write_point('foam_trigger', True)
        self.poll(StationPhase.WAIT_FOAM_RESET)

    def test_recipe_out_of_tolerance_locks_station(self):
        self.vision.measured = (130.0, 150.0)
        self.poll(StationPhase.WAIT_RACK)
        self.plc.write_point('rack_barcode', 'RK-DB100-RCPNG')
        self.pulse('rack_trigger', StationPhase.WAIT_RACK_RESET, StationPhase.WAIT_RECIPE_VERIFY)
        self.plc.write_point('recipe_verify_trigger', True)
        cycle = self.poll(StationPhase.LOCKED)
        self.assertFalse(cycle.recipe_verified)
        self.assertFalse(self.plc.read_point('boxing_allowed'))
        self.assertTrue(self.plc.read_point('recipe_verify_done'))
