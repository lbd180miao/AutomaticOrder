# 3D SDK Frontend Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the rack-location SDK debug drawer and configure formal camera capture from `3d_SDK/tofconfig` while retaining the independent camera development page and backend camera APIs.

**Architecture:** Add a focused decoder/validator that converts the vendor's XOR-encoded JSON into the existing camera SDK arguments. `DMCameraService` consumes this file at connection time, while the rack-location business page keeps only production controls. The independent `/dm-camera/` development page, its view and template, and all `/dm-camera/api/*` routes remain intact.

**Tech Stack:** Python 3, Django 6, `unittest`, Django test client, vanilla JavaScript, Django templates

---

### Task 1: Decode and validate the vendor configuration file

**Files:**
- Create: `apps/dm_camera/tofconfig.py`
- Modify: `apps/dm_camera/tests.py`
- Read at runtime: `3d_SDK/tofconfig`

- [ ] **Step 1: Write failing decoder and validation tests**

Add these imports and tests to `apps/dm_camera/tests.py`:

```python
import json
from tempfile import TemporaryDirectory

from apps.dm_camera.tofconfig import TofConfigError, load_tof_config


class TofConfigTests(TestCase):
    def write_config(self, directory, payload):
        path = Path(directory) / 'tofconfig'
        plain = json.dumps(payload).encode('utf-8')
        path.write_bytes(bytes(value ^ 0xFF for value in plain))
        return path

    def valid_payload(self):
        return {
            'fps_value': 10,
            'exposure_time': [1004],
            'trigger_mode': 0,
            'is_confidence_filtering': False,
            'confidence_filter_value': 15,
            'is_fly_filtering': False,
            'fly_filter_value': 5,
            'is_spatial_filtering': False,
            'spatial_filter_value': 2,
        }

    def test_load_tof_config_decodes_and_maps_vendor_fields(self):
        with TemporaryDirectory() as directory:
            config = load_tof_config(self.write_config(directory, self.valid_payload()))

        self.assertEqual(config.frame_rate, 10)
        self.assertEqual(config.exposure_time, 1004)
        self.assertEqual(config.trigger_mode, 'ACTIVE')
        self.assertEqual(config.confidence, (False, 15))
        self.assertEqual(config.flying_pixels, (False, 5))
        self.assertEqual(config.spatial, (False, 2))

    def test_load_tof_config_rejects_missing_file(self):
        with self.assertRaisesRegex(TofConfigError, 'not found'):
            load_tof_config(Path('missing-tofconfig'))

    def test_load_tof_config_rejects_invalid_json(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'tofconfig'
            path.write_bytes(bytes(value ^ 0xFF for value in b'not-json'))
            with self.assertRaisesRegex(TofConfigError, 'invalid JSON'):
                load_tof_config(path)

    def test_load_tof_config_rejects_invalid_required_fields(self):
        payload = self.valid_payload()
        payload['exposure_time'] = []
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(TofConfigError, 'exposure_time'):
                load_tof_config(self.write_config(directory, payload))
```

- [ ] **Step 2: Run tests and verify the new module is missing**

Run: `.\.venv\Scripts\python.exe manage.py test apps.dm_camera.tests.TofConfigTests`

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.dm_camera.tofconfig'`.

- [ ] **Step 3: Implement the minimal decoder and validator**

Create `apps/dm_camera/tofconfig.py`:

```python
import json
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


class TofConfigError(ValueError):
    pass


@dataclass(frozen=True)
class TofCameraConfig:
    frame_rate: int
    exposure_time: int
    trigger_mode: str
    confidence: tuple[bool, int]
    flying_pixels: tuple[bool, int]
    spatial: tuple[bool, int]


TRIGGER_MODES = {0: 'ACTIVE', 1: 'SOFT', 2: 'HARD'}


def _required_int(payload, key):
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TofConfigError(f'invalid {key}')
    return value


def _required_bool(payload, key):
    value = payload.get(key)
    if not isinstance(value, bool):
        raise TofConfigError(f'invalid {key}')
    return value


def load_tof_config(path=None):
    config_path = Path(path) if path else Path(settings.BASE_DIR) / '3d_SDK' / 'tofconfig'
    try:
        encoded = config_path.read_bytes()
    except FileNotFoundError as exc:
        raise TofConfigError(f'tofconfig not found: {config_path}') from exc

    try:
        payload = json.loads(bytes(value ^ 0xFF for value in encoded).decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TofConfigError(f'tofconfig invalid JSON: {config_path}') from exc

    exposure = payload.get('exposure_time')
    if not isinstance(exposure, list) or not exposure:
        raise TofConfigError('invalid exposure_time')
    trigger_value = _required_int(payload, 'trigger_mode')
    if trigger_value not in TRIGGER_MODES:
        raise TofConfigError('invalid trigger_mode')

    return TofCameraConfig(
        frame_rate=_required_int(payload, 'fps_value'),
        exposure_time=int(exposure[0]),
        trigger_mode=TRIGGER_MODES[trigger_value],
        confidence=(
            _required_bool(payload, 'is_confidence_filtering'),
            _required_int(payload, 'confidence_filter_value'),
        ),
        flying_pixels=(
            _required_bool(payload, 'is_fly_filtering'),
            _required_int(payload, 'fly_filter_value'),
        ),
        spatial=(
            _required_bool(payload, 'is_spatial_filtering'),
            _required_int(payload, 'spatial_filter_value'),
        ),
    )
```

- [ ] **Step 4: Run the focused tests**

Run: `.\.venv\Scripts\python.exe manage.py test apps.dm_camera.tests.TofConfigTests`

Expected: 4 tests pass.

- [ ] **Step 5: Commit the decoder**

```powershell
git add apps/dm_camera/tofconfig.py apps/dm_camera/tests.py 3d_SDK/tofconfig
git commit -m "feat: load 3d camera parameters from tofconfig"
```

### Task 2: Apply file parameters in the camera service

**Files:**
- Modify: `apps/dm_camera/services.py`
- Modify: `apps/dm_camera/tests.py`

- [ ] **Step 1: Write a failing service mapping test**

Add to `apps/dm_camera/tests.py`:

```python
from apps.dm_camera.tofconfig import TofCameraConfig


class DMCameraTofConfigApplicationTests(TestCase):
    def test_apply_config_uses_tofconfig_values_instead_of_database_imaging_values(self):
        calls = []

        class FakeCamera:
            device_handle = object()
            is_streaming = False

            def configure_camera(self, **kwargs):
                calls.append(('camera', kwargs))

            def set_filters(self, **kwargs):
                calls.append(('filters', kwargs))

        service = DMCameraService()
        service._camera = FakeCamera()
        file_config = TofCameraConfig(
            frame_rate=10,
            exposure_time=1004,
            trigger_mode='ACTIVE',
            confidence=(False, 15),
            flying_pixels=(False, 5),
            spatial=(False, 2),
        )

        with patch('apps.dm_camera.services.load_tof_config', return_value=file_config):
            service._apply_config(object())

        self.assertEqual(calls[0][1]['frame_rate'], 10)
        self.assertEqual(calls[0][1]['exposure_time'], 1004)
        self.assertEqual(calls[1][1]['confidence'], (False, 15))
        self.assertEqual(calls[1][1]['flying_pixels'], (False, 5))
        self.assertEqual(calls[1][1]['spatial'], (False, 2))
```

- [ ] **Step 2: Run the service test and verify it fails**

Run: `.\.venv\Scripts\python.exe manage.py test apps.dm_camera.tests.DMCameraTofConfigApplicationTests`

Expected: FAIL because `apps.dm_camera.services.load_tof_config` does not exist or `_apply_config` reads model attributes.

- [ ] **Step 3: Switch `_apply_config` to the file-backed configuration**

In `apps/dm_camera/services.py`, import `load_tof_config`, load it at the start of `_apply_config`, and map the resulting trigger string through the existing `trigger_mode_map`:

```python
from .tofconfig import load_tof_config

def _apply_config(self, config):
    if not self.is_connected:
        raise DMCameraException('camera is not connected')

    tof_config = load_tof_config()
    trigger_mode_map = {
        'ACTIVE': LWTriggerMode.LW_TRIGGER_ACTIVE,
        'SOFT': LWTriggerMode.LW_TRIGGER_SOFT,
        'HARD': LWTriggerMode.LW_TRIGGER_HARD,
    }
    self._camera.configure_camera(
        frame_rate=tof_config.frame_rate,
        exposure_time=tof_config.exposure_time,
        trigger_mode=trigger_mode_map[tof_config.trigger_mode],
    )
    self._camera.set_filters(
        confidence=tof_config.confidence,
        flying_pixels=tof_config.flying_pixels,
        spatial=tof_config.spatial,
    )
```

Keep the `config` argument because connection sessions still reference `DMCameraConfig`; remove only its use for imaging/filter values.

- [ ] **Step 4: Run decoder, service, and connection recovery tests**

Run: `.\.venv\Scripts\python.exe manage.py test apps.dm_camera.tests.TofConfigTests apps.dm_camera.tests.DMCameraTofConfigApplicationTests apps.dm_camera.tests.DMCameraServiceConnectionRecoveryTests`

Expected: all focused tests pass.

- [ ] **Step 5: Commit service integration**

```powershell
git add apps/dm_camera/services.py apps/dm_camera/tests.py
git commit -m "feat: apply tofconfig during camera connection"
```

### Task 3: Remove the SDK drawer from the rack-location workbench

**Files:**
- Modify: `templates/vision/rack_locator_panel.html`
- Modify: `static/vision/js/rack_locator_workbench.js`
- Modify: `apps/vision/tests.py`
- Modify: `apps/vision/urls.py`
- Modify: `apps/vision/views.py`

- [ ] **Step 1: Change the page test to require absence of SDK development controls**

Replace the SDK-positive assertions in `test_rack_locator_panel_exposes_3d_roi_workbench_controls` with:

```python
for development_marker in (
    'btn-sdk-debug',
    'sdk-debug-drawer',
    'sdk-frame-rate',
    'btn-sdk-save-config',
    'btn-sdk-open-demo',
    'apiSdkFindDevicesUrl',
    'sdkConfigUrl',
    'apiSdkDiagnosticsUrl',
    'apiSdkRecoverUrl',
):
    self.assertNotContains(response, development_marker)

self.assertContains(response, 'api_vision_3d_capture')
self.assertContains(response, 'api_vision_3d_test_locate')
```

Delete `test_vision_3d_sdk_config_api_reads_and_saves_active_global_config`, because that endpoint exists only for the removed editor.

- [ ] **Step 2: Run the page test and verify it fails**

Run: `.\.venv\Scripts\python.exe manage.py test apps.vision.tests.RackLocation3DViewTests.test_rack_locator_panel_exposes_3d_roi_workbench_controls`

Expected: FAIL because `btn-sdk-debug` and other SDK markers are still rendered.

- [ ] **Step 3: Remove SDK-only template content**

In `templates/vision/rack_locator_panel.html`, delete:

- the CSS block beginning with `/* SDK 调试侧边栏 */` and ending before `</style>` while retaining non-SDK page styles;
- the `btn-sdk-debug` button;
- the `sdk-drawer-backdrop` element and entire `sdk-debug-drawer` aside;
- `sdkConfigUrl`, `apiSdkFindDevicesUrl`, `apiSdkDiagnosticsUrl`, and `apiSdkRecoverUrl` from `window.rackLocatorConfig`.

- [ ] **Step 4: Remove SDK-only JavaScript**

In `static/vision/js/rack_locator_workbench.js`, delete SDK state and helpers (`sdkConfigId`, `setSdkStatus`, `setSdkTile`, `setSdkPreviewMeta`, `sdkConfigPayload`, `fillSdkConfig`, `loadSdkConfig`, `saveSdkConfig`, `refreshSdkDiagnostics`, `runSdkCaptureTest`) and every `btn-sdk-*` event listener. Preserve capture, ROI, calculation, history, and unified response handling.

- [ ] **Step 5: Remove the frontend-only SDK config endpoint**

Delete the `api/vision/3d/sdk-config/` path from `apps/vision/urls.py`. Delete `_serialize_dm_camera_config`, `_default_dm_camera_config_payload`, and `api_vision_3d_sdk_config` from `apps/vision/views.py`, then remove the now-unused `DMCameraConfig` import from that file. The separate import in `apps/vision/rack_location.py` remains unchanged for production device selection.

- [ ] **Step 6: Run page and 3D API tests**

Run: `.\.venv\Scripts\python.exe manage.py test apps.vision.tests.RackLocation3DViewTests apps.vision.tests.Rack3DLocatorApiTests`

Expected: tests pass and production 3D endpoints remain covered.

- [ ] **Step 7: Commit the workbench cleanup**

```powershell
git add templates/vision/rack_locator_panel.html static/vision/js/rack_locator_workbench.js apps/vision/tests.py apps/vision/urls.py apps/vision/views.py
git commit -m "refactor: remove 3d sdk controls from workbench"
```

### Task 4: Verify the independent camera development page remains

> **Scope update:** The user cancelled the former Task 4 that removed the independent camera page. Do not delete or alter the root demo route, `views.demo_page`, `templates/dm_camera_demo.html`, or any `/dm-camera/api/*` route as part of this work.

**Files:**
- Verify: `apps/dm_camera/urls.py`
- Verify: `apps/dm_camera/views.py`
- Verify: `templates/dm_camera_demo.html`
- Test: `apps/dm_camera/tests.py`

- [ ] **Step 1: Verify the route, view, template, and APIs remain**

Run:

```powershell
Test-Path templates/dm_camera_demo.html
rg -n "path\('', views\.demo_page|path\('api/" apps/dm_camera/urls.py
rg -n "def demo_page" apps/dm_camera/views.py
```

Expected: `Test-Path` returns `True`; the root route resolves to `views.demo_page`; `demo_page` remains defined; API routes are listed.

- [ ] **Step 2: Run the existing demo-page and API tests**

Run: `.\.venv\Scripts\python.exe manage.py test apps.dm_camera`

Expected: the suite passes, including coverage that `/dm-camera/` returns HTTP 200 (or equivalent route-resolution coverage) and retained API routes still work.

- [ ] **Step 3: Treat any removal as a regression**

If the root demo route, view, template, or any `/dm-camera/api/*` route is missing, stop and restore it before completing the frontend cleanup. Do not execute the cancelled page-removal task.

### Task 5: Verify the retained production surface

**Files:**
- Verify only; fix failures in the files changed by Tasks 1–4

- [ ] **Step 1: Scan for removed frontend markers**

Run: `rg -n "btn-sdk-debug|sdk-debug-drawer|sdkConfigUrl|apiSdk" templates/vision/rack_locator_panel.html static/vision/js/rack_locator_workbench.js`

Expected: no matches in the rack-location template or JavaScript. `templates/dm_camera_demo.html` is intentionally retained and is not part of this removal scan.

- [ ] **Step 2: Verify required backend routes remain**

Run: `rg -n "path\('', views\.demo_page|api/devices/find|api/connect|api/capture|api/status" apps/dm_camera/urls.py`

Expected: the root demo route and all four representative API routes are present.

- [ ] **Step 3: Run Django system checks**

Run: `.\.venv\Scripts\python.exe manage.py check`

Expected: `System check identified no issues`.

- [ ] **Step 4: Run the affected test suites**

Run: `.\.venv\Scripts\python.exe manage.py test apps.dm_camera apps.vision`

Expected: all tests pass.

- [ ] **Step 5: Inspect the final diff**

Run: `git diff --check` and `git status --short`

Expected: no whitespace errors; only intended implementation files and unrelated pre-existing user changes appear.

- [ ] **Step 6: Record verification outcome**

If every command passed, leave the tree unchanged and record the commands and pass counts in the handoff. If a command failed, return to the task that owns the failing file, add a focused regression test, make the minimal correction, and rerun that task before repeating Steps 1–5.
