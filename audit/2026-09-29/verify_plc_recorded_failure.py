"""Replay an existing failed camera frame against an in-memory PLC only."""
import json
from pathlib import Path
from unittest.mock import patch

from apps.devices.adapters.plc import MemoryPLCTransport, PLCAdapter
from apps.devices.plc_position_debug import capture_position, step
from apps.vision.models import RackLocationRecipe
from apps.vision.rack_location import RackLocationService

frame = Path('media/vision/rack_workbench/2026/09/29/rack_workbench_081444_339882.npy')
assert frame.is_file(), 'Recorded failure frame is missing'
recipe = RackLocationRecipe.objects.get(pk=8)
plc = PLCAdapter(transport=MemoryPLCTransport())
plc.connect()
state = {'phase': 'ARMING', 'recipe_id': recipe.pk, 'layer_no': 1}
step(state, plc, capture_position)
plc.write_point('position_trigger', True)
calculation = RackLocationService.calculate_workbench


def calculate_without_record(service, **kwargs):
    kwargs['save_record'] = False
    return calculation(service, **kwargs)


with patch('apps.vision.rack_location.Rack3DLocator.capture', return_value={
    'source': 'rvc_camera', 'pointcloud_token': frame.relative_to('media').as_posix(),
}), patch.object(RackLocationService, 'calculate_workbench', calculate_without_record):
    step(state, plc, capture_position)

actual = {axis: plc.read_point(f'layer_delta_{axis}') for axis in 'xyz'}
assert actual == dict.fromkeys('xyz', 999.0), actual
assert plc.read_point('position_success') is False
assert plc.read_point('position_done') is True
assert 'Π1' in state['error']
report = {
    'verification': 'Recorded real camera frame + production calculation + in-memory Siemens DB2 transport',
    'physical_plc_accessed': False,
    'new_camera_capture': False,
    'source_frame': str(frame),
    'recipe_id': recipe.pk,
    'error': state['error'],
    'readback': {'DB2.DBD50': actual['x'], 'DB2.DBD54': actual['y'], 'DB2.DBD58': actual['z'],
                 'DB2.DBX49.2': False, 'DB2.DBX49.1': True},
    'state': state,
}
Path('audit/2026-09-29/plc-recorded-failure-report.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8',
)
print(json.dumps(report, ensure_ascii=True, indent=2))
