# Single Rack 3-Layer 3D Location Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the existing 3D rack-location module for a single rack with global positioning plus three layer positioning cycles.

**Architecture:** Keep the current `apps.vision` models and services, add a compatibility layer that exposes `locate_type` and `layer_index` while preserving `layer_no` and `mode=global/local`. Store new overall/layer/final compensation details in `RackLocationResult.result_data` first, avoiding a risky schema rewrite unless a later migration is explicitly required.

**Tech Stack:** Django 6, SQLite test database, Django test client, NumPy point-cloud helpers, existing `Rack3DLocator`, `RackLocationRecipe`, `RackLocationROI3D`, `RackLocationResult`, existing template and vanilla JavaScript workbench.

---

## File Structure

- Modify `apps/vision/rack_location.py`
  - Add semantic helpers for `locate_type`, `layer_index`, ROI mode mapping, and result payload enrichment.
  - Add current recipe lookup, ROI save with alignment-token guard, latest valid global result lookup, global/layer compensation composition, and PLC payload enrichment.
- Modify `apps/vision/views.py`
  - Add formal API endpoints: camera test, align alias, current recipe, recipe save alias, locate, latest result, results.
  - Update existing recipe/ROI serializers to include `locate_type` and `layer_index`.
  - Update ROI save endpoint to accept `locate_type/layer_index/alignment_token`.
- Modify `apps/vision/urls.py`
  - Add formal routes under existing `/vision/api/vision/3d/...`.
- Modify `apps/vision/tests.py`
  - Add service and API tests before implementation.
  - Add template/JS source tests for workbench state machine markers.
- Modify `templates/vision/rack_locator_panel.html`
  - Add `layer_index=0..3`, `locate_type=GLOBAL/LAYER`, view-mode selectors, and initially disabled action buttons.
  - Pass the new URLs into `window.rackLocatorConfig`.
- Modify `static/vision/js/rack_locator_workbench.js`
  - Add explicit UI state machine and button enablement rules.
  - Send `locate_type`, `layer_index`, `alignment_token`, and 3D ROI to backend.
- No planned migration in the first implementation pass.
  - New semantics are stored in existing fields and `result_data`.
  - If tests reveal that a physical column is necessary, add a focused `apps/vision/migrations/0008_*.py` in a later task.

## Task 1: Add Semantic Mapping Helpers

**Files:**
- Modify: `apps/vision/rack_location.py`
- Test: `apps/vision/tests.py`

- [ ] **Step 1: Write the failing tests**

Append these tests near existing 3D rack-location service tests in `apps/vision/tests.py`:

```python
class Rack3DSemanticMappingTests(SimpleTestCase):
    def test_normalize_locate_type_accepts_global_and_layer(self):
        from apps.vision.rack_location import normalize_locate_type

        self.assertEqual(normalize_locate_type('global'), 'GLOBAL')
        self.assertEqual(normalize_locate_type('LAYER'), 'LAYER')

    def test_normalize_locate_type_rejects_unknown_values(self):
        from apps.vision.rack_location import normalize_locate_type

        with self.assertRaisesMessage(ValueError, 'locate_type must be GLOBAL or LAYER'):
            normalize_locate_type('SIDE')

    def test_normalize_layer_index_enforces_global_zero_and_layers_one_to_three(self):
        from apps.vision.rack_location import normalize_layer_index

        self.assertEqual(normalize_layer_index(0, 'GLOBAL'), 0)
        self.assertEqual(normalize_layer_index('3', 'LAYER'), 3)

        with self.assertRaisesMessage(ValueError, 'GLOBAL locate_type requires layer_index=0'):
            normalize_layer_index(1, 'GLOBAL')
        with self.assertRaisesMessage(ValueError, 'LAYER locate_type requires layer_index 1, 2, or 3'):
            normalize_layer_index(0, 'LAYER')

    def test_locate_semantics_map_to_existing_roi_fields(self):
        from apps.vision.rack_location import locate_semantics

        self.assertEqual(
            locate_semantics(locate_type='GLOBAL', layer_index=0),
            {'locate_type': 'GLOBAL', 'layer_index': 0, 'roi_mode': 'global', 'layer_no': 0},
        )
        self.assertEqual(
            locate_semantics(locate_type='LAYER', layer_index=2),
            {'locate_type': 'LAYER', 'layer_index': 2, 'roi_mode': 'local', 'layer_no': 2},
        )
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DSemanticMappingTests
```

Expected: FAIL with import errors for `normalize_locate_type`, `normalize_layer_index`, or `locate_semantics`.

- [ ] **Step 3: Implement the minimal helpers**

Add this near the top of `apps/vision/rack_location.py`, after `_decimal`:

```python
LOCATE_TYPE_GLOBAL = 'GLOBAL'
LOCATE_TYPE_LAYER = 'LAYER'


def normalize_locate_type(value: Any = None) -> str:
    locate_type = str(value or LOCATE_TYPE_LAYER).strip().upper()
    if locate_type not in {LOCATE_TYPE_GLOBAL, LOCATE_TYPE_LAYER}:
        raise ValueError('locate_type must be GLOBAL or LAYER')
    return locate_type


def normalize_layer_index(value: Any = None, locate_type: Any = None) -> int:
    normalized_type = normalize_locate_type(locate_type)
    if value in (None, ''):
        layer_index = 0 if normalized_type == LOCATE_TYPE_GLOBAL else 1
    else:
        try:
            layer_index = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError('layer_index must be an integer') from exc

    if normalized_type == LOCATE_TYPE_GLOBAL and layer_index != 0:
        raise ValueError('GLOBAL locate_type requires layer_index=0')
    if normalized_type == LOCATE_TYPE_LAYER and layer_index not in {1, 2, 3}:
        raise ValueError('LAYER locate_type requires layer_index 1, 2, or 3')
    return layer_index


def locate_semantics(*, locate_type: Any = None, layer_index: Any = None,
                     layer_no: Any = None, mode: Any = None) -> dict:
    if locate_type is None and mode:
        locate_type = LOCATE_TYPE_GLOBAL if str(mode).lower() == RackLocationROI3D.MODE_GLOBAL else LOCATE_TYPE_LAYER
    normalized_type = normalize_locate_type(locate_type)
    index_value = layer_index if layer_index not in (None, '') else layer_no
    normalized_index = normalize_layer_index(index_value, normalized_type)
    return {
        'locate_type': normalized_type,
        'layer_index': normalized_index,
        'roi_mode': RackLocationROI3D.MODE_GLOBAL if normalized_type == LOCATE_TYPE_GLOBAL else RackLocationROI3D.MODE_LOCAL,
        'layer_no': normalized_index,
    }
```

- [ ] **Step 4: Run the tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DSemanticMappingTests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/vision/rack_location.py apps/vision/tests.py
git commit -m "feat: add 3d rack location semantics"
```

## Task 2: Enrich Serializers and Result Payloads

**Files:**
- Modify: `apps/vision/rack_location.py`
- Modify: `apps/vision/views.py`
- Test: `apps/vision/tests.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
class Rack3DSerializationSemanticsTests(TestCase):
    def setUp(self):
        self.recipe = RackLocationRecipe.objects.create(
            recipe_name='SER-GLOBAL',
            rack_side='BOTH',
            position_no=1,
            layer_no=0,
            layer_count=3,
            standard_x=0,
            standard_y=0,
            standard_z=850,
            hand_eye_config={'matrix': 'identity'},
        )
        self.task = VisionTask.objects.create(
            task_type=VisionTaskType.RACK_LOCATING,
            status=ResultStatus.SUCCESS,
        )

    def test_recipe_serializer_exposes_locate_type_and_layer_index(self):
        from apps.vision.views import _serialize_3d_recipe

        payload = _serialize_3d_recipe(self.recipe)

        self.assertEqual(payload['locate_type'], 'GLOBAL')
        self.assertEqual(payload['layer_index'], 0)
        self.assertEqual(payload['total_layers'], 3)
        self.assertEqual(payload['photo_pose_name'], '')

    def test_result_payload_exposes_overall_layer_and_final_offsets(self):
        result = RackLocationResult.objects.create(
            vision_task=self.task,
            recipe=self.recipe,
            side='BOTH',
            position_no=1,
            layer_no=2,
            offset_x=1,
            offset_y=2,
            offset_z=3,
            offset_rz=0.4,
            confidence=0.91,
            is_success=True,
            result_data={
                'locate_type': 'LAYER',
                'layer_index': 2,
                'overall_offset': {'x': 10, 'y': 20, 'z': 30, 'rz': 1.5},
                'layer_offset': {'x': 1, 'y': 2, 'z': 3, 'rz': 0.4},
                'final_offset': {'x': 11, 'y': 22, 'z': 33, 'rz': 1.9},
            },
        )

        payload = rack_location_result_payload(result)

        self.assertEqual(payload['locate_type'], 'LAYER')
        self.assertEqual(payload['layer_index'], 2)
        self.assertEqual(payload['overall_offset_x'], 10.0)
        self.assertEqual(payload['layer_offset_x'], 1.0)
        self.assertEqual(payload['final_offset_x'], 11.0)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DSerializationSemanticsTests
```

Expected: FAIL because serializers do not expose the new fields.

- [ ] **Step 3: Update serializers**

In `apps/vision/views.py`, update `_serialize_3d_recipe(recipe)` so its returned dict includes:

```python
semantics = locate_semantics(
    locate_type='GLOBAL' if int(recipe.layer_no or 0) == 0 else 'LAYER',
    layer_index=int(recipe.layer_no or 0),
)
payload.update({
    'locate_type': semantics['locate_type'],
    'layer_index': semantics['layer_index'],
    'total_layers': int(recipe.layer_count or 3),
    'photo_pose_name': recipe.capture_pose_name,
    'robot_pose_code': (recipe.reference_feature_config or {}).get('robot_pose_code', ''),
})
```

Also import `locate_semantics` from `.rack_location`.

In `_serialize_3d_roi(roi)`, add:

```python
semantics = locate_semantics(mode=roi.mode, layer_index=roi.layer_no or 0)
payload.update({
    'locate_type': semantics['locate_type'],
    'layer_index': semantics['layer_index'],
})
```

- [ ] **Step 4: Update result payload**

In `apps/vision/rack_location.py`, extend `result_payload(result)`:

```python
data = result.result_data or {}
locate_type = data.get('locate_type') or ('GLOBAL' if int(result.layer_no or 0) == 0 else 'LAYER')
layer_index = int(data.get('layer_index', result.layer_no or 0))
overall = data.get('overall_offset') or {}
layer = data.get('layer_offset') or {}
final = data.get('final_offset') or {}
```

Add these keys to the returned dict:

```python
'locate_type': locate_type,
'layer_index': layer_index,
'overall_offset_x': float(overall.get('x', result.offset_x if locate_type == 'GLOBAL' else 0)),
'overall_offset_y': float(overall.get('y', result.offset_y if locate_type == 'GLOBAL' else 0)),
'overall_offset_z': float(overall.get('z', result.offset_z if locate_type == 'GLOBAL' else 0)),
'overall_offset_rz': float(overall.get('rz', result.offset_rz if locate_type == 'GLOBAL' else 0)),
'layer_offset_x': float(layer.get('x', result.offset_x if locate_type == 'LAYER' else 0)),
'layer_offset_y': float(layer.get('y', result.offset_y if locate_type == 'LAYER' else 0)),
'layer_offset_z': float(layer.get('z', result.offset_z if locate_type == 'LAYER' else 0)),
'layer_offset_rz': float(layer.get('rz', result.offset_rz if locate_type == 'LAYER' else 0)),
'final_offset_x': float(final.get('x', result.offset_x)),
'final_offset_y': float(final.get('y', result.offset_y)),
'final_offset_z': float(final.get('z', result.offset_z)),
'final_offset_rz': float(final.get('rz', result.offset_rz)),
```

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DSerializationSemanticsTests
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add apps/vision/rack_location.py apps/vision/views.py apps/vision/tests.py
git commit -m "feat: expose 3d location semantic payloads"
```

## Task 3: Add Current Recipe and Guarded ROI Save

**Files:**
- Modify: `apps/vision/rack_location.py`
- Modify: `apps/vision/views.py`
- Modify: `apps/vision/urls.py`
- Test: `apps/vision/tests.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
@override_settings(MEDIA_ROOT=mkdtemp())
class Rack3DCurrentRecipeAndRoiApiTests(TestCase):
    def setUp(self):
        self.global_recipe = RackLocationRecipe.objects.create(
            recipe_name='CUR-GLOBAL',
            rack_side='BOTH',
            position_no=1,
            layer_no=0,
            layer_count=3,
            standard_x=0,
            standard_y=0,
            standard_z=850,
            hand_eye_config={'matrix': 'identity'},
        )
        self.layer_recipe = RackLocationRecipe.objects.create(
            recipe_name='CUR-L2',
            rack_side='BOTH',
            position_no=1,
            layer_no=2,
            layer_count=3,
            standard_x=0,
            standard_y=0,
            standard_z=900,
            hand_eye_config={'matrix': 'identity'},
        )

    def test_current_recipe_api_uses_locate_type_and_layer_index(self):
        response = self.client.get(
            reverse('vision:api_vision_3d_recipe_current'),
            {'locate_type': 'GLOBAL', 'layer_index': '0'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['data']['recipe']['id'], self.global_recipe.id)
        self.assertEqual(payload['data']['recipe']['locate_type'], 'GLOBAL')
        self.assertEqual(payload['data']['recipe']['layer_index'], 0)

    def test_save_roi_requires_alignment_token(self):
        response = self.client.post(
            reverse('vision:api_vision_3d_rois'),
            data=json.dumps({
                'recipe_id': self.layer_recipe.id,
                'locate_type': 'LAYER',
                'layer_index': 2,
                'x_min': -10,
                'x_max': 10,
                'y_min': -10,
                'y_max': 10,
                'z_min': 700,
                'z_max': 950,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
        self.assertIn('请先自动对齐', response.json()['error'])

    def test_save_roi_accepts_alignment_token_and_maps_layer_semantics(self):
        token = 'vision/rack_workbench/aligned.npy'
        path = Path(settings.MEDIA_ROOT) / token
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, np.zeros((2, 2, 3), dtype=np.float32))

        response = self.client.post(
            reverse('vision:api_vision_3d_rois'),
            data=json.dumps({
                'recipe_id': self.layer_recipe.id,
                'alignment_token': token,
                'locate_type': 'LAYER',
                'layer_index': 2,
                'roi_name': '第2层ROI',
                'x_min': -10,
                'x_max': 10,
                'y_min': -10,
                'y_max': 10,
                'z_min': 700,
                'z_max': 950,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        roi = RackLocationROI3D.objects.get(recipe=self.layer_recipe)
        self.assertEqual(roi.mode, RackLocationROI3D.MODE_LOCAL)
        self.assertEqual(roi.layer_no, 2)
        self.assertEqual(response.json()['data']['roi']['locate_type'], 'LAYER')
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DCurrentRecipeAndRoiApiTests
```

Expected: FAIL because `api_vision_3d_recipe_current` route and guarded ROI save do not exist.

- [ ] **Step 3: Add service methods**

In `Rack3DLocator`, add:

```python
def _media_token_exists(self, token: str) -> bool:
    if not token:
        return False
    media_root = os.path.realpath(settings.MEDIA_ROOT)
    abs_path = os.path.realpath(os.path.join(media_root, token))
    return os.path.commonpath([abs_path, media_root]) == media_root and os.path.exists(abs_path)

def get_current_recipe(self, *, locate_type, layer_index, rack_type=None):
    semantics = locate_semantics(locate_type=locate_type, layer_index=layer_index)
    qs = RackLocationRecipe.objects.filter(enabled=True, layer_no=semantics['layer_no'])
    if rack_type:
        qs = qs.filter(rack_type=rack_type)
    return qs.order_by('position_no', '-updated_at').first()

def save_roi(self, *, recipe_id, locate_type, layer_index, roi_3d, alignment_token,
             roi_name='3D ROI', enabled=True):
    if not self._media_token_exists(alignment_token):
        raise ValueError('请先自动对齐，再保存生产 ROI')
    semantics = locate_semantics(locate_type=locate_type, layer_index=layer_index)
    recipe = RackLocationRecipe.objects.get(pk=recipe_id)
    RackLocationROI3D.objects.filter(
        recipe=recipe,
        mode=semantics['roi_mode'],
        layer_no=None if semantics['roi_mode'] == RackLocationROI3D.MODE_GLOBAL else semantics['layer_no'],
        enabled=True,
    ).update(enabled=False)
    return RackLocationROI3D.objects.create(
        recipe=recipe,
        roi_name=roi_name,
        mode=semantics['roi_mode'],
        layer_no=None if semantics['roi_mode'] == RackLocationROI3D.MODE_GLOBAL else semantics['layer_no'],
        coordinate_system='rack',
        x_min=roi_3d['x_min'],
        x_max=roi_3d['x_max'],
        y_min=roi_3d['y_min'],
        y_max=roi_3d['y_max'],
        z_min=roi_3d['z_min'],
        z_max=roi_3d['z_max'],
        enabled=enabled,
    )
```

- [ ] **Step 4: Add views and routes**

In `apps/vision/views.py`, add:

```python
@require_http_methods(['GET'])
def api_vision_3d_recipe_current(request):
    try:
        recipe = Rack3DLocator().get_current_recipe(
            locate_type=request.GET.get('locate_type') or 'LAYER',
            layer_index=request.GET.get('layer_index') or request.GET.get('layer_no') or 1,
            rack_type=request.GET.get('rack_type') or None,
        )
        return _api3d_success({'recipe': _serialize_3d_recipe(recipe) if recipe else None})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)
```

Update `api_vision_3d_rois` POST branch:

```python
data = _request_data(request)
if data.get('locate_type') or data.get('layer_index') is not None:
    roi = Rack3DLocator().save_roi(
        recipe_id=data.get('recipe_id'),
        locate_type=data.get('locate_type') or 'LAYER',
        layer_index=data.get('layer_index') if data.get('layer_index') is not None else data.get('layer_no'),
        alignment_token=data.get('alignment_token') or data.get('aligned_pointcloud_token'),
        roi_name=data.get('roi_name') or data.get('name') or '3D ROI',
        roi_3d={
            'x_min': data.get('x_min'),
            'x_max': data.get('x_max'),
            'y_min': data.get('y_min'),
            'y_max': data.get('y_max'),
            'z_min': data.get('z_min'),
            'z_max': data.get('z_max'),
        },
        enabled=_as_bool(data.get('enabled'), True),
    )
    return _api3d_success({'roi': _serialize_3d_roi(roi)})
```

In `apps/vision/urls.py`, add before recipe detail route:

```python
path('api/vision/3d/recipes/current/', views.api_vision_3d_recipe_current, name='api_vision_3d_recipe_current'),
```

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DCurrentRecipeAndRoiApiTests
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add apps/vision/rack_location.py apps/vision/views.py apps/vision/urls.py apps/vision/tests.py
git commit -m "feat: add current 3d recipe and guarded roi save"
```

## Task 4: Add Formal Camera Test, Align Alias, Locate, and Result APIs

**Files:**
- Modify: `apps/vision/views.py`
- Modify: `apps/vision/urls.py`
- Test: `apps/vision/tests.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
@override_settings(MEDIA_ROOT=mkdtemp(), VISION_RACK_LOCATION_FORCE_SAMPLE=True)
class Rack3DFormalApiFlowTests(TestCase):
    def setUp(self):
        self.recipe = RackLocationRecipe.objects.create(
            recipe_name='FLOW-GLOBAL',
            rack_side='BOTH',
            position_no=1,
            layer_no=0,
            layer_count=3,
            standard_x=0,
            standard_y=0,
            standard_z=850,
            max_offset_x=9999,
            max_offset_y=9999,
            max_offset_z=9999,
            confidence_threshold=0.1,
            hand_eye_config={'matrix': 'identity'},
        )

    def test_camera_test_api_returns_online_boolean(self):
        response = self.client.post(reverse('vision:api_vision_3d_camera_test'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertIn('online', payload['data'])

    def test_align_alias_accepts_capture_token(self):
        capture = self.client.post(
            reverse('vision:api_vision_3d_capture'),
            data=json.dumps({'recipe_id': self.recipe.id, 'locate_type': 'GLOBAL', 'layer_index': 0}),
            content_type='application/json',
        ).json()

        response = self.client.post(
            reverse('vision:api_vision_3d_align'),
            data=json.dumps({'pointcloud_token': capture['data']['pointcloud_token'], 'recipe_id': self.recipe.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['data']['aligned_pointcloud_token'])

    def test_results_latest_api_returns_latest_result(self):
        task = VisionTask.objects.create(task_type=VisionTaskType.RACK_LOCATING, status=ResultStatus.SUCCESS)
        RackLocationResult.objects.create(
            vision_task=task,
            recipe=self.recipe,
            side='BOTH',
            position_no=1,
            layer_no=0,
            confidence=0.9,
            is_success=True,
            result_data={'locate_type': 'GLOBAL', 'layer_index': 0},
        )

        response = self.client.get(reverse('vision:api_vision_3d_results_latest'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['result']['locate_type'], 'GLOBAL')
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DFormalApiFlowTests
```

Expected: FAIL because the new route names are missing.

- [ ] **Step 3: Implement formal views**

Add to `apps/vision/views.py`:

```python
@require_POST
def api_vision_3d_camera_test(request):
    try:
        from apps.dm_camera.services import DMCameraService
        status = DMCameraService().get_status()
        return _api3d_success({
            'online': bool(status.get('connected') or status.get('streaming')),
            'status': status,
        })
    except Exception as exc:  # noqa: BLE001
        return _api3d_success({
            'online': False,
            'status': {'error': str(exc)},
        })


@require_POST
def api_vision_3d_align(request):
    return api_vision_3d_auto_align(request)


@require_POST
def api_vision_3d_locate(request):
    try:
        data = _request_data(request)
        semantics = locate_semantics(
            locate_type=data.get('locate_type') or ('GLOBAL' if _as_int(data.get('layer_index'), 1) == 0 else 'LAYER'),
            layer_index=data.get('layer_index') if data.get('layer_index') is not None else data.get('layer_no'),
        )
        result = Rack3DLocator().locate(
            rack_side=data.get('rack_side') or 'BOTH',
            layer_no=semantics['layer_no'],
            recipe_id=data.get('recipe_id') or None,
            write_plc=_as_bool(data.get('write_plc'), False),
        )
        return _api3d_success({'result': rack_location_result_payload(result)})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_http_methods(['GET'])
def api_vision_3d_results_latest(request):
    result = (
        RackLocationResult.objects
        .select_related('recipe', 'vision_task')
        .order_by('-created_at')
        .first()
    )
    return _api3d_success({'result': rack_location_result_payload(result) if result else None})


@require_http_methods(['GET'])
def api_vision_3d_results(request):
    qs = RackLocationResult.objects.select_related('recipe', 'vision_task').order_by('-created_at')
    locate_type = request.GET.get('locate_type')
    layer_index = request.GET.get('layer_index')
    if layer_index not in (None, ''):
        qs = qs.filter(layer_no=int(layer_index))
    if locate_type:
        expected = normalize_locate_type(locate_type)
        qs = [r for r in qs[:200] if (r.result_data or {}).get('locate_type') == expected or (expected == 'GLOBAL' and int(r.layer_no or 0) == 0) or (expected == 'LAYER' and int(r.layer_no or 0) in {1, 2, 3})]
        return _api3d_success({'results': [rack_location_result_payload(result) for result in qs]})
    return _api3d_success({'results': [rack_location_result_payload(result) for result in qs[:100]]})
```

Also import `normalize_locate_type` and `locate_semantics` in `views.py`.

- [ ] **Step 4: Add routes**

Add to `apps/vision/urls.py`:

```python
path('api/vision/3d/camera/test/', views.api_vision_3d_camera_test, name='api_vision_3d_camera_test'),
path('api/vision/3d/align/', views.api_vision_3d_align, name='api_vision_3d_align'),
path('api/vision/3d/locate/', views.api_vision_3d_locate, name='api_vision_3d_locate'),
path('api/vision/3d/results/latest/', views.api_vision_3d_results_latest, name='api_vision_3d_results_latest'),
path('api/vision/3d/results/', views.api_vision_3d_results, name='api_vision_3d_results'),
```

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DFormalApiFlowTests
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add apps/vision/views.py apps/vision/urls.py apps/vision/tests.py
git commit -m "feat: add formal 3d rack location apis"
```

## Task 5: Compose Global and Layer Final Compensation

**Files:**
- Modify: `apps/vision/rack_location.py`
- Test: `apps/vision/tests.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
@override_settings(MEDIA_ROOT=mkdtemp(), VISION_RACK_LOCATION_FORCE_SAMPLE=True)
class Rack3DGlobalLayerCompensationTests(TestCase):
    class Provider:
        def capture(self, recipe, position_no, layer_no):
            from apps.vision.rack_location import build_sample_pointcloud
            return {'source': 'sample', 'organized_pointcloud': build_sample_pointcloud(side='LEFT', layer_count=3)}

    def setUp(self):
        self.global_recipe = RackLocationRecipe.objects.create(
            recipe_name='COMP-GLOBAL',
            rack_side='BOTH',
            position_no=1,
            layer_no=0,
            layer_count=3,
            standard_x=0,
            standard_y=0,
            standard_z=850,
            max_offset_x=9999,
            max_offset_y=9999,
            max_offset_z=9999,
            confidence_threshold=0.1,
            hand_eye_config={'matrix': 'identity'},
        )
        self.layer_recipe = RackLocationRecipe.objects.create(
            recipe_name='COMP-L1',
            rack_side='BOTH',
            position_no=1,
            layer_no=1,
            layer_count=3,
            standard_x=0,
            standard_y=0,
            standard_z=850,
            max_offset_x=9999,
            max_offset_y=9999,
            max_offset_z=9999,
            confidence_threshold=0.1,
            hand_eye_config={'matrix': 'identity'},
        )
        for recipe, mode, layer_no in (
            (self.global_recipe, 'global', None),
            (self.layer_recipe, 'local', 1),
        ):
            RackLocationROI3D.objects.create(
                recipe=recipe,
                roi_name=f'{mode}-roi',
                mode=mode,
                layer_no=layer_no,
                x_min=-500,
                x_max=500,
                y_min=-300,
                y_max=300,
                z_min=500,
                z_max=1400,
            )

    def test_global_locate_records_overall_offset(self):
        result = Rack3DLocator(frame_provider=self.Provider()).locate(
            rack_side='BOTH',
            layer_no=0,
            recipe_id=self.global_recipe.id,
            write_plc=False,
        )

        self.assertEqual(result.result_data['locate_type'], 'GLOBAL')
        self.assertEqual(result.result_data['layer_index'], 0)
        self.assertIn('overall_offset', result.result_data)
        self.assertEqual(result.result_data['final_offset'], result.result_data['overall_offset'])

    def test_layer_locate_combines_latest_global_and_layer_offset(self):
        global_task = VisionTask.objects.create(task_type=VisionTaskType.RACK_LOCATING, status=ResultStatus.SUCCESS)
        RackLocationResult.objects.create(
            vision_task=global_task,
            recipe=self.global_recipe,
            side='BOTH',
            position_no=1,
            layer_no=0,
            offset_x=10,
            offset_y=20,
            offset_z=30,
            offset_rz=1,
            confidence=0.95,
            is_success=True,
            result_data={
                'locate_type': 'GLOBAL',
                'layer_index': 0,
                'overall_offset': {'x': 10, 'y': 20, 'z': 30, 'rz': 1},
                'final_offset': {'x': 10, 'y': 20, 'z': 30, 'rz': 1},
            },
        )

        result = Rack3DLocator(frame_provider=self.Provider()).locate(
            rack_side='BOTH',
            layer_no=1,
            recipe_id=self.layer_recipe.id,
            write_plc=False,
        )

        data = result.result_data
        self.assertEqual(data['locate_type'], 'LAYER')
        self.assertEqual(data['layer_index'], 1)
        self.assertAlmostEqual(data['final_offset']['x'], data['overall_offset']['x'] + data['layer_offset']['x'])
        self.assertAlmostEqual(data['final_offset']['rz'], data['overall_offset']['rz'] + data['layer_offset']['rz'])
        self.assertEqual(data['plc_payload']['final_offset_x'], data['final_offset']['x'])
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DGlobalLayerCompensationTests
```

Expected: FAIL because `result_data` does not yet include the required overall/layer/final structure.

- [ ] **Step 3: Implement compensation helpers**

In `Rack3DLocator`, add:

```python
def _offset_dict(self, output: RackLocationOutput) -> dict:
    return {
        'x': float(output.offset_x),
        'y': float(output.offset_y),
        'z': float(output.offset_z),
        'rz': float(output.offset_rz),
    }

def _latest_global_result(self, *, rack_side, position_no):
    return (
        RackLocationResult.objects
        .filter(
            side=rack_side,
            position_no=position_no,
            layer_no=0,
            is_success=True,
            result_data__locate_type='GLOBAL',
        )
        .order_by('-created_at')
        .first()
    )

def _combine_offsets(self, overall: dict, layer: dict) -> dict:
    return {
        'x': round(float(overall.get('x', 0)) + float(layer.get('x', 0)), 3),
        'y': round(float(overall.get('y', 0)) + float(layer.get('y', 0)), 3),
        'z': round(float(overall.get('z', 0)) + float(layer.get('z', 0)), 3),
        'rz': round(float(overall.get('rz', 0)) + float(layer.get('rz', 0)), 3),
    }

def _semantic_result_data(self, *, output, recipe, rack_side, layer_no, roi, roi_source, token):
    semantics = locate_semantics(
        locate_type='GLOBAL' if int(layer_no) == 0 else 'LAYER',
        layer_index=int(layer_no),
    )
    current_offset = self._offset_dict(output)
    if semantics['locate_type'] == 'GLOBAL':
        overall = current_offset
        layer = {'x': 0.0, 'y': 0.0, 'z': 0.0, 'rz': 0.0}
        final = overall
    else:
        global_result = self._latest_global_result(rack_side=rack_side, position_no=int(recipe.position_no or 1))
        overall = (global_result.result_data or {}).get('overall_offset') if global_result else {}
        layer = current_offset
        final = self._combine_offsets(overall or {}, layer)
    payload = output.to_payload()
    payload['plc_payload'].update({
        'locate_type': semantics['locate_type'],
        'layer_index': semantics['layer_index'],
        'final_offset_x': final['x'],
        'final_offset_y': final['y'],
        'final_offset_z': final['z'],
        'final_offset_rz': final['rz'],
        'compensation_valid': output.locate_ok,
    })
    return {
        **(payload.get('result_data') or {}),
        'task_kind': 'RACK_3D_LOCATION',
        'locate_type': semantics['locate_type'],
        'layer_index': semantics['layer_index'],
        'roi_id': getattr(roi, 'id', None),
        'roi_source': roi_source,
        'overall_offset': overall,
        'layer_offset': layer,
        'final_offset': final,
        'pointcloud_token': token,
        'plc_payload': payload['plc_payload'],
    }
```

- [ ] **Step 4: Use the helper in `Rack3DLocator.locate`**

Replace the existing `result_data={...}` creation in `locate()` with:

```python
result_data = self._semantic_result_data(
    output=output,
    recipe=recipe,
    rack_side=rack_side,
    layer_no=int(layer_no),
    roi=roi,
    roi_source=roi_source,
    token=captured.get('pointcloud_token', ''),
)
```

Then pass `result_data=result_data` to `RackLocationResult.objects.create(...)`.

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DGlobalLayerCompensationTests
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add apps/vision/rack_location.py apps/vision/tests.py
git commit -m "feat: compose global and layer 3d offsets"
```

## Task 6: Enforce PLC Valid Compensation Rules

**Files:**
- Modify: `apps/vision/rack_location.py`
- Test: `apps/vision/tests.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
class Rack3DPlcPayloadSafetyTests(TestCase):
    def test_ng_result_writes_compensation_valid_false(self):
        task = VisionTask.objects.create(task_type=VisionTaskType.RACK_LOCATING, status=ResultStatus.FAILED)
        result = RackLocationResult.objects.create(
            vision_task=task,
            side='BOTH',
            position_no=1,
            layer_no=1,
            offset_x=999,
            offset_y=0,
            offset_z=0,
            offset_rz=0,
            confidence=0.2,
            is_success=False,
            error_code='LOW_CONFIDENCE',
            result_data={
                'locate_type': 'LAYER',
                'layer_index': 1,
                'final_offset': {'x': 999, 'y': 0, 'z': 0, 'rz': 0},
                'plc_payload': {
                    'locate_ok': False,
                    'compensation_valid': True,
                    'final_offset_x': 999,
                },
            },
        )

        payload = rack_location_result_payload(result)['plc_payload']

        self.assertFalse(payload['locate_ok'])
        self.assertFalse(payload['compensation_valid'])
        self.assertEqual(payload['error_code'], 'LOW_CONFIDENCE')
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DPlcPayloadSafetyTests
```

Expected: FAIL because stale `result_data.plc_payload.compensation_valid=True` may leak through.

- [ ] **Step 3: Normalize PLC payload in `result_payload`**

In `result_payload(result)`, after reading `plc_payload`, normalize:

```python
plc_payload = dict(result.result_data.get('plc_payload') or {})
plc_payload.update({
    'locate_ok': bool(result.is_success),
    'compensation_valid': bool(result.is_success),
    'error_code': result.error_code,
})
if 'final_offset_x' not in plc_payload:
    plc_payload.update({
        'final_offset_x': float(final.get('x', result.offset_x)),
        'final_offset_y': float(final.get('y', result.offset_y)),
        'final_offset_z': float(final.get('z', result.offset_z)),
        'final_offset_rz': float(final.get('rz', result.offset_rz)),
    })
```

Return `'plc_payload': plc_payload`.

- [ ] **Step 4: Add write-time guard**

In `Rack3DLocator.write_result_to_plc(result)` or `PlcVisionResultWriter.write(result)`, before sending to adapter:

```python
if not result.is_success:
    result.plc_write_status = 'SKIPPED'
    result.plc_error_message = '定位 NG，禁止写入有效补偿'
    result.save(update_fields=['plc_write_status', 'plc_error_message', 'updated_at'])
    return {'success': False, 'error': result.plc_error_message, 'skipped': True}
```

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DPlcPayloadSafetyTests
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add apps/vision/rack_location.py apps/vision/tests.py
git commit -m "fix: prevent valid plc compensation for ng 3d results"
```

## Task 7: Add Frontend State Machine and Semantic Controls

**Files:**
- Modify: `templates/vision/rack_locator_panel.html`
- Modify: `static/vision/js/rack_locator_workbench.js`
- Test: `apps/vision/tests.py`

- [ ] **Step 1: Write the failing source tests**

Append:

```python
class Rack3DWorkbenchStateSourceTests(SimpleTestCase):
    def test_template_contains_locate_type_and_layer_index_controls(self):
        source = (Path(settings.BASE_DIR) / 'templates' / 'vision' / 'rack_locator_panel.html').read_text(encoding='utf-8')

        self.assertIn('id="locate-type"', source)
        self.assertIn('id="layer-index"', source)
        self.assertIn('value="0"', source)
        self.assertIn('整体定位', source)

    def test_javascript_has_explicit_workflow_state_machine(self):
        source = (Path(settings.BASE_DIR) / 'static' / 'vision' / 'js' / 'rack_locator_workbench.js').read_text(encoding='utf-8')

        self.assertIn('workflowState', source)
        self.assertIn('setWorkflowState', source)
        self.assertIn('roi_saved', source)
        self.assertIn('aligned', source)
        self.assertIn('located_ng', source)
        self.assertIn('alignment_token', source)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DWorkbenchStateSourceTests
```

Expected: FAIL because template and JS do not yet contain those markers.

- [ ] **Step 3: Update template controls**

In `templates/vision/rack_locator_panel.html`, replace the existing mode/layer manual controls with:

```html
<span class="ctrl-label" style="color:var(--text);">定位类型</span>
<select id="locate-type" aria-label="定位类型">
  <option value="GLOBAL">整体定位</option>
  <option value="LAYER" selected>层定位</option>
</select>
<span class="ctrl-label" style="color:var(--text);">layer_index</span>
<select id="layer-index" aria-label="定位层号">
  <option value="0">0 · 整体</option>
  <option value="1" selected>1 · 第1层</option>
  <option value="2">2 · 第2层</option>
  <option value="3">3 · 第3层</option>
</select>
```

Keep the old `layer-no` and `layer-no-select` elements only if needed for compatibility; if kept, mark them hidden and synchronize from `layer-index`.

Add disabled attributes to buttons:

```html
<button id="btn-auto-align" class="btn btn-secondary" disabled>自动对齐</button>
<button id="btn-redraw" class="btn btn-secondary" disabled>重画 ROI</button>
<button id="btn-calculate" class="btn btn-success" style="background:var(--success);" disabled>🎯 计算偏差</button>
<button id="btn-save-roi" class="btn btn-secondary" disabled>保存 ROI</button>
<button id="btn-write-plc" class="btn btn-secondary" disabled>写入 PLC</button>
```

Add config URLs:

```javascript
cameraTestUrl: '{% url "vision:api_vision_3d_camera_test" %}',
alignUrl: '{% url "vision:api_vision_3d_align" %}',
currentRecipeUrl: '{% url "vision:api_vision_3d_recipe_current" %}',
locateUrl: '{% url "vision:api_vision_3d_locate" %}',
resultsLatestUrl: '{% url "vision:api_vision_3d_results_latest" %}',
formalResultsUrl: '{% url "vision:api_vision_3d_results" %}',
```

- [ ] **Step 4: Update JavaScript state machine**

In `static/vision/js/rack_locator_workbench.js`, extend state:

```javascript
workflowState: 'idle',
alignmentToken: null,
roiSaved: false,
lastLocateOk: false,
```

Add helpers:

```javascript
function currentLocateType() {
  return $('locate-type')?.value || (currentLayerIndex() === 0 ? 'GLOBAL' : 'LAYER');
}

function currentLayerIndex() {
  return numberInput('layer-index', currentLayerNo());
}

function setWorkflowState(next) {
  state.workflowState = next;
  const captured = ['captured', 'aligned', 'roi_saved', 'located_ok', 'located_ng', 'plc_written'].includes(next);
  const aligned = ['aligned', 'roi_saved', 'located_ok', 'located_ng', 'plc_written'].includes(next);
  const roiSaved = ['roi_saved', 'located_ok', 'located_ng', 'plc_written'].includes(next);
  const locatedOk = ['located_ok', 'plc_written'].includes(next);
  if ($('btn-auto-align')) $('btn-auto-align').disabled = !captured;
  if ($('btn-redraw')) $('btn-redraw').disabled = !captured;
  if ($('btn-save-roi')) $('btn-save-roi').disabled = !aligned;
  if ($('btn-calculate')) $('btn-calculate').disabled = !roiSaved;
  if ($('btn-write-plc')) $('btn-write-plc').disabled = !locatedOk || !state.lastResultId;
}
```

Call `setWorkflowState('captured')` after successful capture, `setWorkflowState('aligned')` after successful align, `setWorkflowState('roi_saved')` after successful ROI save, `setWorkflowState(result.locate_ok ? 'located_ok' : 'located_ng')` after calculation, and `setWorkflowState('plc_written')` after successful PLC write.

Update request bodies:

```javascript
locate_type: currentLocateType(),
layer_index: currentLayerIndex(),
alignment_token: state.alignmentToken,
```

Set `state.alignmentToken` from align response:

```javascript
state.alignmentToken = data.aligned_pointcloud_token || data.pointcloud_token || state.token;
```

- [ ] **Step 5: Run source tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DWorkbenchStateSourceTests
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add templates/vision/rack_locator_panel.html static/vision/js/rack_locator_workbench.js apps/vision/tests.py
git commit -m "feat: add 3d workbench workflow state"
```

## Task 8: Run Focused and Regression Verification

**Files:**
- No source edits unless a test failure reveals a defect.

- [ ] **Step 1: Run focused 3D tests**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DSemanticMappingTests apps.vision.tests.Rack3DSerializationSemanticsTests apps.vision.tests.Rack3DCurrentRecipeAndRoiApiTests apps.vision.tests.Rack3DFormalApiFlowTests apps.vision.tests.Rack3DGlobalLayerCompensationTests apps.vision.tests.Rack3DPlcPayloadSafetyTests apps.vision.tests.Rack3DWorkbenchStateSourceTests
```

Expected: all PASS.

- [ ] **Step 2: Run existing vision tests**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision
```

Expected: all PASS. If failures occur in unrelated dirty-worktree changes, record the exact failing tests and inspect whether this feature caused them before changing code.

- [ ] **Step 3: Run Django system check**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py check
```

Expected: `System check identified no issues`.

- [ ] **Step 4: Inspect git diff**

Run:

```powershell
git diff -- apps/vision/rack_location.py apps/vision/views.py apps/vision/urls.py apps/vision/tests.py templates/vision/rack_locator_panel.html static/vision/js/rack_locator_workbench.js
```

Expected: diff only contains single-rack 3D semantic, API, compensation, and workbench state changes.

- [ ] **Step 5: Commit verification fixes if any**

If Step 1-4 require fixes:

```powershell
git add apps/vision/rack_location.py apps/vision/views.py apps/vision/urls.py apps/vision/tests.py templates/vision/rack_locator_panel.html static/vision/js/rack_locator_workbench.js
git commit -m "test: verify single rack 3d location flow"
```

If no source fixes are needed, do not create an empty commit.

## Self-Review

Spec coverage:

- Single rack, three layers: covered by semantic helpers, current recipe lookup, front-end `layer_index=0..3`.
- `locate_type + layer_index`: covered in helpers, serializers, APIs, JS requests.
- 3D ROI only after auto-align: covered by guarded ROI save and front-end state machine.
- Overall plus layer final compensation: covered by Task 5.
- NG blocks valid PLC compensation: covered by Task 6.
- Current recipe and latest result APIs: covered by Tasks 3 and 4.
- Existing module reuse: all tasks modify existing `apps/vision` files only.

Placeholder scan:

- No `TBD`, `TODO`, `implement later`, or open-ended test instructions.

Type consistency:

- Public semantic names are consistently `locate_type`, `layer_index`, `GLOBAL`, `LAYER`.
- Internal compatibility names remain `layer_no`, `mode`, `global`, `local`.
- Result offset structures consistently use `overall_offset`, `layer_offset`, `final_offset` with keys `x`, `y`, `z`, `rz`.

