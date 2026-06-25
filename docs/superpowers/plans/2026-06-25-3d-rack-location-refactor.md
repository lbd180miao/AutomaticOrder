# 3D Rack Location Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing 3D rack-location workbench to use persistent rack-coordinate 3D ROI recipes and expose formal `/api/vision/3d/...` APIs while keeping old `api/rack-location/...` endpoints compatible.

**Architecture:** Add `RackLocationROI3D` as the durable ROI table, then introduce `Rack3DLocator` as the formal service facade for capture, alignment, corrected views, 3D ROI cropping, test location, production location, and PLC write. Existing `RackLocationService` and old views stay in place and delegate to the new flow where practical.

**Tech Stack:** Django, Django TestCase/SimpleTestCase, SQLite-compatible migrations, NumPy/OpenCV point-cloud helpers, Django templates, vanilla JavaScript.

---

## Scope Check

The approved spec is one coherent subsystem: 3D rack location inside `apps/vision`. It includes model, service, API, and workbench UI changes that must ship together for a useful vertical slice. It deliberately excludes 2D foam inspection, MES, production workflow rewrites, and real hardware algorithm replacement.

## File Structure

- Modify `apps/vision/models.py`: add `RackLocationROI3D` with validation for global/local layer semantics and spatial min/max ranges.
- Create `apps/vision/migrations/0007_racklocationroi3d.py`: schema for `RackLocationROI3D`.
- Modify `apps/vision/admin.py`: register `RackLocationROI3D`.
- Modify `apps/vision/rack_location.py`: add 3D ROI serialization helpers, `PointCloudProcessor.crop_by_roi_3d()`, `Rack3DLocator`, and compatibility delegation from `RackLocationService`.
- Modify `apps/vision/views.py`: add formal `/api/vision/3d/...` JSON views and serializers; keep old endpoints working.
- Modify `apps/vision/urls.py`: add formal API routes.
- Modify `apps/vision/tests.py`: add model, point-cloud, service, API, compatibility, and template tests. Before editing, inspect current unstaged changes in this file and preserve them.
- Modify `templates/vision/rack_locator_panel.html`: add rack side, mode, layer, six 3D ROI fields, new action buttons, and new API config.
- Modify `static/vision/js/rack_locator_workbench.js`: drive capture, auto-align, test-locate, ROI save, and PLC write against the new APIs while preserving old capture/calculate behavior where needed.
- Optionally modify `templates/vision/rack_location_recipes.html` and `templates/vision/rack_location_recipe_form.html`: expose 3D ROI summary or link into the workbench if the template test requires it.

## Pre-Execution Guard

- [ ] **Step 1: Inspect dirty files before implementation**

Run:

```powershell
git status --short
git diff -- apps/vision/tests.py
```

Expected: `apps/vision/tests.py` may already be modified. Preserve those changes. When committing tasks that touch `apps/vision/tests.py`, use `git add -p apps/vision/tests.py` if unrelated pre-existing hunks remain.

- [ ] **Step 2: Verify baseline**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.RackLocationRecipe3DModelTests apps.vision.tests.RackLocationPointCloudProcessorTests apps.vision.tests.RackLocationService3DTests apps.vision.tests.RackLocation3DViewTests apps.vision.tests.RackLocationWorkbenchTests -v 2
```

Expected: `manage.py check` passes. Existing 3D tests should pass before new work starts; if they fail, record the failure and fix or ask before continuing.

## Task 1: 3D ROI Model, Migration, Admin

**Files:**
- Modify: `apps/vision/tests.py`
- Modify: `apps/vision/models.py`
- Create: `apps/vision/migrations/0007_racklocationroi3d.py`
- Modify: `apps/vision/admin.py`

- [ ] **Step 1: Write failing model tests**

Add this test class near `RackLocationRecipe3DModelTests` in `apps/vision/tests.py`:

```python
class RackLocationROI3DModelTests(TestCase):
    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        self.recipe = Recipe.objects.create(
            recipe_name='ROI3D-POS-01-L1',
            rack_side='LEFT',
            position_no=1,
            layer_no=1,
            standard_x=0,
            standard_y=0,
            standard_z=0,
            hand_eye_config={'matrix': 'identity'},
        )

    def test_global_and_local_roi_store_rack_coordinate_bounds(self):
        ROI = apps.get_model('vision', 'RackLocationROI3D')

        global_roi = ROI.objects.create(
            recipe=self.recipe,
            roi_name='左料架全局ROI',
            mode='global',
            layer_no=None,
            coordinate_system='rack',
            x_min=-300,
            x_max=300,
            y_min=-150,
            y_max=150,
            z_min=700,
            z_max=1100,
        )
        local_roi = ROI.objects.create(
            recipe=self.recipe,
            roi_name='左料架第1层ROI',
            mode='local',
            layer_no=1,
            coordinate_system='rack',
            x_min=-120,
            x_max=120,
            y_min=-80,
            y_max=80,
            z_min=820,
            z_max=900,
        )

        self.assertEqual(global_roi.mode, 'global')
        self.assertIsNone(global_roi.layer_no)
        self.assertEqual(local_roi.layer_no, 1)
        self.assertEqual(float(local_roi.x_min), -120.0)
        self.assertEqual(float(local_roi.z_max), 900.0)

    def test_roi_rejects_invalid_spatial_bounds(self):
        ROI = apps.get_model('vision', 'RackLocationROI3D')
        roi = ROI(
            recipe=self.recipe,
            roi_name='无效ROI',
            mode='local',
            layer_no=1,
            x_min=10,
            x_max=10,
            y_min=0,
            y_max=20,
            z_min=0,
            z_max=20,
        )

        with self.assertRaisesMessage(ValidationError, 'x_min must be less than x_max'):
            roi.full_clean()

    def test_local_roi_requires_layer_and_global_roi_clears_layer(self):
        ROI = apps.get_model('vision', 'RackLocationROI3D')

        local_roi = ROI(
            recipe=self.recipe,
            roi_name='缺少层号',
            mode='local',
            layer_no=None,
            x_min=0,
            x_max=10,
            y_min=0,
            y_max=10,
            z_min=0,
            z_max=10,
        )
        with self.assertRaisesMessage(ValidationError, 'local ROI requires layer_no'):
            local_roi.full_clean()

        global_roi = ROI.objects.create(
            recipe=self.recipe,
            roi_name='自动清空层号',
            mode='global',
            layer_no=2,
            x_min=0,
            x_max=10,
            y_min=0,
            y_max=10,
            z_min=0,
            z_max=10,
        )
        self.assertIsNone(global_roi.layer_no)
```

Also add `ValidationError` to the top imports in `apps/vision/tests.py`:

```python
from django.core.exceptions import ValidationError
```

- [ ] **Step 2: Run model tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.RackLocationROI3DModelTests -v 2
```

Expected: FAIL because `RackLocationROI3D` does not exist.

- [ ] **Step 3: Add the model**

In `apps/vision/models.py`, add this class after `RackLocationRecipe` and before `RackLocationResult`:

```python
class RackLocationROI3D(TimeStampedModel):
    MODE_GLOBAL = 'global'
    MODE_LOCAL = 'local'
    MODE_CHOICES = (
        (MODE_GLOBAL, '全局定位'),
        (MODE_LOCAL, '局部定位'),
    )

    recipe = models.ForeignKey(
        RackLocationRecipe,
        on_delete=models.CASCADE,
        related_name='rois_3d',
    )
    roi_name = models.CharField(max_length=128)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES)
    layer_no = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    coordinate_system = models.CharField(max_length=32, default='rack')
    x_min = models.DecimalField(max_digits=10, decimal_places=3)
    x_max = models.DecimalField(max_digits=10, decimal_places=3)
    y_min = models.DecimalField(max_digits=10, decimal_places=3)
    y_max = models.DecimalField(max_digits=10, decimal_places=3)
    z_min = models.DecimalField(max_digits=10, decimal_places=3)
    z_max = models.DecimalField(max_digits=10, decimal_places=3)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ['recipe_id', 'mode', 'layer_no', '-updated_at']
        indexes = [
            models.Index(fields=['recipe', 'mode', 'layer_no', 'enabled']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['recipe'],
                condition=models.Q(mode='global', enabled=True),
                name='unique_enabled_global_3d_roi_per_recipe',
            ),
            models.UniqueConstraint(
                fields=['recipe', 'layer_no'],
                condition=models.Q(mode='local', enabled=True),
                name='unique_enabled_local_3d_roi_per_recipe_layer',
            ),
            models.CheckConstraint(
                check=models.Q(x_min__lt=models.F('x_max')),
                name='rack_3d_roi_x_min_lt_x_max',
            ),
            models.CheckConstraint(
                check=models.Q(y_min__lt=models.F('y_max')),
                name='rack_3d_roi_y_min_lt_y_max',
            ),
            models.CheckConstraint(
                check=models.Q(z_min__lt=models.F('z_max')),
                name='rack_3d_roi_z_min_lt_z_max',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.mode == self.MODE_GLOBAL:
            self.layer_no = None
        elif self.mode == self.MODE_LOCAL and self.layer_no is None:
            errors['layer_no'] = 'local ROI requires layer_no'

        if self.x_min is not None and self.x_max is not None and self.x_min >= self.x_max:
            errors['x_min'] = 'x_min must be less than x_max'
        if self.y_min is not None and self.y_max is not None and self.y_min >= self.y_max:
            errors['y_min'] = 'y_min must be less than y_max'
        if self.z_min is not None and self.z_max is not None and self.z_min >= self.z_max:
            errors['z_min'] = 'z_min must be less than z_max'
        if errors:
            from django.core.exceptions import ValidationError
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        layer = f'L{self.layer_no}' if self.layer_no else 'GLOBAL'
        return f'{self.recipe.recipe_name}:{self.mode}:{layer}:{self.roi_name}'
```

- [ ] **Step 4: Add migration**

Create `apps/vision/migrations/0007_racklocationroi3d.py`:

```python
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('vision', '0006_add_actual_coordinates'),
    ]

    operations = [
        migrations.CreateModel(
            name='RackLocationROI3D',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('roi_name', models.CharField(max_length=128)),
                ('mode', models.CharField(choices=[('global', '全局定位'), ('local', '局部定位')], max_length=16)),
                ('layer_no', models.PositiveIntegerField(blank=True, db_index=True, null=True)),
                ('coordinate_system', models.CharField(default='rack', max_length=32)),
                ('x_min', models.DecimalField(decimal_places=3, max_digits=10)),
                ('x_max', models.DecimalField(decimal_places=3, max_digits=10)),
                ('y_min', models.DecimalField(decimal_places=3, max_digits=10)),
                ('y_max', models.DecimalField(decimal_places=3, max_digits=10)),
                ('z_min', models.DecimalField(decimal_places=3, max_digits=10)),
                ('z_max', models.DecimalField(decimal_places=3, max_digits=10)),
                ('enabled', models.BooleanField(default=True)),
                ('recipe', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rois_3d', to='vision.racklocationrecipe')),
            ],
            options={
                'ordering': ['recipe_id', 'mode', 'layer_no', '-updated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='racklocationroi3d',
            index=models.Index(fields=['recipe', 'mode', 'layer_no', 'enabled'], name='vision_rack_recipe_5a2f0d_idx'),
        ),
        migrations.AddConstraint(
            model_name='racklocationroi3d',
            constraint=models.UniqueConstraint(condition=models.Q(('mode', 'global'), ('enabled', True)), fields=('recipe',), name='unique_enabled_global_3d_roi_per_recipe'),
        ),
        migrations.AddConstraint(
            model_name='racklocationroi3d',
            constraint=models.UniqueConstraint(condition=models.Q(('mode', 'local'), ('enabled', True)), fields=('recipe', 'layer_no'), name='unique_enabled_local_3d_roi_per_recipe_layer'),
        ),
        migrations.AddConstraint(
            model_name='racklocationroi3d',
            constraint=models.CheckConstraint(check=models.Q(('x_min__lt', models.F('x_max'))), name='rack_3d_roi_x_min_lt_x_max'),
        ),
        migrations.AddConstraint(
            model_name='racklocationroi3d',
            constraint=models.CheckConstraint(check=models.Q(('y_min__lt', models.F('y_max'))), name='rack_3d_roi_y_min_lt_y_max'),
        ),
        migrations.AddConstraint(
            model_name='racklocationroi3d',
            constraint=models.CheckConstraint(check=models.Q(('z_min__lt', models.F('z_max'))), name='rack_3d_roi_z_min_lt_z_max'),
        ),
    ]
```

- [ ] **Step 5: Register admin**

Modify `apps/vision/admin.py` imports to include `RackLocationROI3D`:

```python
from .models import (
    CalibrationProfile,
    FoamInspectionResult,
    RackLocationROI3D,
    RackLocationRecipe,
    RackLocationResult,
    VisionImage,
    VisionRecipe,
    VisionTask,
)
```

Add this admin class after `RackLocationRecipeAdmin`:

```python
@admin.register(RackLocationROI3D)
class RackLocationROI3DAdmin(admin.ModelAdmin):
    list_display = (
        'roi_name', 'recipe', 'mode', 'layer_no', 'coordinate_system',
        'x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max', 'enabled',
    )
    list_filter = ('enabled', 'mode', 'coordinate_system', 'layer_no')
    search_fields = ('roi_name', 'recipe__recipe_name')
```

- [ ] **Step 6: Run model tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.RackLocationROI3DModelTests -v 2
.\.venv\Scripts\python.exe manage.py check
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1**

Run:

```powershell
git add apps/vision/models.py apps/vision/admin.py apps/vision/migrations/0007_racklocationroi3d.py
git add -p apps/vision/tests.py
git commit -m "feat: add 3d rack ROI model"
```

Expected: commit succeeds. If `apps/vision/tests.py` had unrelated pre-existing hunks, only stage the hunks from this task.

## Task 2: 3D Spatial ROI Point-Cloud Cropping

**Files:**
- Modify: `apps/vision/tests.py`
- Modify: `apps/vision/rack_location.py`

- [ ] **Step 1: Write failing point-cloud tests**

Add these tests to `RackLocationPointCloudProcessorTests` in `apps/vision/tests.py`:

```python
    def test_crop_by_roi_3d_filters_points_inside_spatial_box(self):
        from apps.vision.rack_location import PointCloudProcessor

        pointcloud = np.array([
            [[0, 0, 10], [5, 5, 15], [20, 0, 10]],
            [[2, 4, 12], [9, 9, 19], [np.nan, 1, 1]],
        ], dtype=float)
        processor = PointCloudProcessor()

        points = processor.crop_by_roi_3d(pointcloud, {
            'x_min': 0,
            'x_max': 10,
            'y_min': 0,
            'y_max': 10,
            'z_min': 10,
            'z_max': 20,
        })

        self.assertEqual(points.shape, (4, 3))
        self.assertTrue(np.all(points[:, 0] >= 0))
        self.assertTrue(np.all(points[:, 0] <= 10))
        self.assertTrue(np.all(points[:, 2] >= 10))
        self.assertTrue(np.all(points[:, 2] <= 20))

    def test_crop_by_roi_3d_rejects_invalid_bounds(self):
        from apps.vision.rack_location import PointCloudProcessor

        pointcloud = np.zeros((2, 2, 3), dtype=float)

        with self.assertRaisesMessage(ValueError, 'x_min must be less than x_max'):
            PointCloudProcessor().crop_by_roi_3d(pointcloud, {
                'x_min': 5,
                'x_max': 5,
                'y_min': 0,
                'y_max': 10,
                'z_min': 0,
                'z_max': 10,
            })
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.RackLocationPointCloudProcessorTests -v 2
```

Expected: FAIL because `PointCloudProcessor.crop_by_roi_3d` does not exist.

- [ ] **Step 3: Add spatial ROI helpers**

In `apps/vision/rack_location.py`, add these methods inside `PointCloudProcessor` after `crop_by_roi()`:

```python
    def _normalized_roi_3d(self, roi: dict) -> dict:
        required = ('x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max')
        try:
            normalized = {key: float(roi[key]) for key in required}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('三维 ROI 参数无效') from exc

        if normalized['x_min'] >= normalized['x_max']:
            raise ValueError('x_min must be less than x_max')
        if normalized['y_min'] >= normalized['y_max']:
            raise ValueError('y_min must be less than y_max')
        if normalized['z_min'] >= normalized['z_max']:
            raise ValueError('z_min must be less than z_max')
        return normalized

    def crop_by_roi_3d(self, organized_pointcloud, roi: dict):
        pointcloud = np.asarray(organized_pointcloud, dtype=float)
        if pointcloud.ndim == 3 and pointcloud.shape[2] == 3:
            points = pointcloud.reshape(-1, 3)
        elif pointcloud.ndim == 2 and pointcloud.shape[1] == 3:
            points = pointcloud
        else:
            raise ValueError('pointcloud 必须是 H x W x 3 或 N x 3')

        valid_points = self.filter_valid_points(points)
        bounds = self._normalized_roi_3d(roi)
        mask = (
            (valid_points[:, 0] >= bounds['x_min'])
            & (valid_points[:, 0] <= bounds['x_max'])
            & (valid_points[:, 1] >= bounds['y_min'])
            & (valid_points[:, 1] <= bounds['y_max'])
            & (valid_points[:, 2] >= bounds['z_min'])
            & (valid_points[:, 2] <= bounds['z_max'])
        )
        return valid_points[mask]
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.RackLocationPointCloudProcessorTests -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add apps/vision/rack_location.py
git add -p apps/vision/tests.py
git commit -m "feat: crop point clouds by 3d ROI"
```

Expected: commit succeeds.

## Task 3: Rack3DLocator Core Service

**Files:**
- Modify: `apps/vision/tests.py`
- Modify: `apps/vision/rack_location.py`

- [ ] **Step 1: Write failing service tests for capture, align, test-locate, and production ROI selection**

Add this test class after `RackLocationWorkbenchTests` in `apps/vision/tests.py`:

```python
@override_settings(MEDIA_ROOT=mkdtemp())
class Rack3DLocatorServiceTests(TestCase):
    class CloudFrameProvider:
        def capture(self, recipe, position_no, layer_no):
            from apps.vision.rack_location import build_sample_pointcloud
            return {
                'source': 'dm_camera',
                'organized_pointcloud': build_sample_pointcloud(side='LEFT', layer_count=3),
            }

    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        ROI = apps.get_model('vision', 'RackLocationROI3D')
        self.recipe = Recipe.objects.create(
            recipe_name='LOCATOR-LEFT-L1',
            rack_side='LEFT',
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
        self.global_roi = ROI.objects.create(
            recipe=self.recipe,
            roi_name='全局ROI',
            mode='global',
            x_min=-500,
            x_max=500,
            y_min=-300,
            y_max=300,
            z_min=500,
            z_max=1400,
        )
        self.local_roi = ROI.objects.create(
            recipe=self.recipe,
            roi_name='第1层ROI',
            mode='local',
            layer_no=1,
            x_min=-250,
            x_max=250,
            y_min=-180,
            y_max=180,
            z_min=650,
            z_max=1200,
        )

    def _locator(self):
        from apps.vision.rack_location import Rack3DLocator
        return Rack3DLocator(frame_provider=self.CloudFrameProvider())

    def test_capture_returns_token_and_observation_images(self):
        payload = self._locator().capture(recipe_id=self.recipe.id)

        self.assertTrue(payload['pointcloud_token'].endswith('.npy'))
        self.assertTrue(payload['pointcloud_preview_url'])
        self.assertIn('raw_rgb_image_url', payload)
        self.assertIn('raw_depth_image_url', payload)
        self.assertEqual(payload['source'], 'dm_camera')

    def test_auto_align_returns_rack_coordinate_system_and_corrected_views(self):
        captured = self._locator().capture(recipe_id=self.recipe.id)

        payload = self._locator().auto_align(
            token=captured['pointcloud_token'],
            recipe_id=self.recipe.id,
        )

        self.assertEqual(payload['coordinate_system']['name'], 'rack')
        self.assertEqual(payload['coordinate_system']['transform_matrix'][0], [1, 0, 0, 0])
        self.assertTrue(payload['views']['front_view_url'])
        self.assertTrue(payload['views']['top_view_url'])
        self.assertTrue(payload['views']['side_view_url'])

    def test_test_locate_uses_request_roi_without_saving(self):
        captured = self._locator().capture(recipe_id=self.recipe.id)

        payload = self._locator().test_locate(
            token=captured['pointcloud_token'],
            roi_3d={
                'x_min': -250,
                'x_max': 250,
                'y_min': -180,
                'y_max': 180,
                'z_min': 650,
                'z_max': 1200,
            },
            recipe_id=self.recipe.id,
            rack_side='LEFT',
            layer_no=1,
        )

        self.assertIn('offset_x', payload)
        self.assertIn('confidence', payload)
        self.assertEqual(payload['roi_source'], 'request')
        self.assertTrue(payload['cropped_preview_url'])
        self.assertEqual(apps.get_model('vision', 'RackLocationResult').objects.count(), 0)

    def test_locate_loads_local_roi_before_global_roi(self):
        result = self._locator().locate(
            rack_side='LEFT',
            layer_no=1,
            recipe_id=self.recipe.id,
            write_plc=False,
        )

        self.assertEqual(result.side, 'LEFT')
        self.assertEqual(result.result_data['roi_id'], self.local_roi.id)
        self.assertEqual(result.result_data['roi_source'], 'local')
        self.assertIn('plc_payload', result.result_data)
```

- [ ] **Step 2: Run service tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DLocatorServiceTests -v 2
```

Expected: FAIL because `Rack3DLocator` does not exist.

- [ ] **Step 3: Add ROI serializer helpers**

In `apps/vision/rack_location.py`, update imports to include `RackLocationROI3D`:

```python
from .models import RackLocationROI3D, RackLocationRecipe, RackLocationResult, VisionImage, VisionTask
```

Add helper functions near `_decimal()`:

```python
def roi3d_to_dict(roi: RackLocationROI3D | dict) -> dict:
    if isinstance(roi, dict):
        return {
            'x_min': float(roi['x_min']),
            'x_max': float(roi['x_max']),
            'y_min': float(roi['y_min']),
            'y_max': float(roi['y_max']),
            'z_min': float(roi['z_min']),
            'z_max': float(roi['z_max']),
        }
    return {
        'id': roi.id,
        'recipe_id': roi.recipe_id,
        'roi_name': roi.roi_name,
        'mode': roi.mode,
        'layer_no': roi.layer_no,
        'coordinate_system': roi.coordinate_system,
        'x_min': float(roi.x_min),
        'x_max': float(roi.x_max),
        'y_min': float(roi.y_min),
        'y_max': float(roi.y_max),
        'z_min': float(roi.z_min),
        'z_max': float(roi.z_max),
        'enabled': roi.enabled,
    }
```

- [ ] **Step 4: Add Rack3DLocator core class**

In `apps/vision/rack_location.py`, add this class before `RackLocationService`:

```python
class Rack3DLocator:
    """Formal 3D rack-location facade using rack-coordinate 3D ROI boxes."""

    def __init__(self, *, frame_provider=None, processor=None, plc_writer=None):
        self.frame_provider = frame_provider or DMCameraRackFrameProvider()
        self.processor = processor or PointCloudProcessor()
        self.plc_writer = plc_writer or PlcVisionResultWriter()

    def _select_recipe(self, *, recipe_id=None, rack_side=RackSide.LEFT, layer_no=1):
        qs = RackLocationRecipe.objects.filter(enabled=True)
        if recipe_id:
            return qs.get(pk=recipe_id)
        return qs.filter(rack_side=rack_side, layer_no=layer_no).order_by('position_no').first() or qs.get(rack_side=RackSide.BOTH, layer_no=layer_no)

    def _select_roi(self, recipe: RackLocationRecipe, layer_no: int):
        local_roi = (
            RackLocationROI3D.objects
            .filter(recipe=recipe, enabled=True, mode=RackLocationROI3D.MODE_LOCAL, layer_no=layer_no)
            .order_by('-updated_at')
            .first()
        )
        if local_roi:
            return local_roi, 'local'
        global_roi = (
            RackLocationROI3D.objects
            .filter(recipe=recipe, enabled=True, mode=RackLocationROI3D.MODE_GLOBAL)
            .order_by('-updated_at')
            .first()
        )
        if global_roi:
            return global_roi, 'global'
        return None, 'missing'

    def _persist_frame(self, pointcloud):
        return RackLocationService(
            frame_provider=self.frame_provider,
            plc_writer=self.plc_writer,
        )._persist_workbench_frame(pointcloud)

    def _load_pointcloud(self, token):
        return RackLocationService(
            frame_provider=self.frame_provider,
            plc_writer=self.plc_writer,
        )._load_workbench_pointcloud(token)

    def capture(self, *, recipe_id=None, rack_side=RackSide.LEFT, layer_no=1) -> dict:
        recipe = self._select_recipe(recipe_id=recipe_id, rack_side=rack_side, layer_no=layer_no) if recipe_id else None
        position_no = int(getattr(recipe, 'position_no', 1) or 1)
        layer_no = int(getattr(recipe, 'layer_no', layer_no) or layer_no)
        layer_count = int(getattr(recipe, 'layer_count', 3) or 3)
        side = str(getattr(recipe, 'rack_side', rack_side) or rack_side).upper()
        side_key = RackSide.RIGHT if side == RackSide.RIGHT else RackSide.LEFT

        pointcloud = None
        source = 'sample'
        fallback_reason = ''
        try:
            probe_recipe = recipe or RackLocationRecipe(
                recipe_name='VISION-3D-CAPTURE',
                rack_side=side_key,
                position_no=position_no,
                layer_no=layer_no,
                layer_count=layer_count,
                hand_eye_config={'matrix': 'identity'},
            )
            frame = self.frame_provider.capture(probe_recipe, position_no, layer_no)
            fallback_reason = frame.get('fallback_reason', '') or ''
            cloud = frame.get('organized_pointcloud')
            if cloud is not None:
                arr = np.asarray(cloud, dtype=float)
                if arr.ndim == 3 and arr.shape[2] == 3:
                    pointcloud = arr
                    source = frame.get('source', 'dm_camera')
        except Exception as exc:  # noqa: BLE001
            fallback_reason = str(exc)

        if pointcloud is None:
            pointcloud = build_sample_pointcloud(side=side_key, layer_count=layer_count)
            source = 'sample'

        token, preview_url, width, height = self._persist_frame(pointcloud)
        return {
            'pointcloud_token': token,
            'pointcloud_preview_url': preview_url,
            'raw_rgb_image_url': preview_url,
            'raw_depth_image_url': preview_url,
            'image_width': width,
            'image_height': height,
            'source': source,
            'fallback_reason': fallback_reason,
        }

    def auto_align(self, *, token, recipe_id=None) -> dict:
        pointcloud = self._load_pointcloud(token)
        views = self.generate_corrected_views(pointcloud)
        return {
            'coordinate_system': {
                'name': 'rack',
                'transform_matrix': [
                    [1, 0, 0, 0],
                    [0, 1, 0, 0],
                    [0, 0, 1, 0],
                    [0, 0, 0, 1],
                ],
                'source': 'mock_identity',
            },
            'features': {
                'columns': [],
                'layers': [],
                'support_plane': {'normal': [0, 0, 1], 'offset': 0},
            },
            'views': views,
        }

    def generate_corrected_views(self, pointcloud) -> dict:
        preview = image_io.pointcloud_to_preview(pointcloud)
        front_rel, _, _ = image_io.save_image(preview, 'rack_3d_front', rel_dir='vision/rack_3d')
        top_rel, _, _ = image_io.save_image(np.flipud(preview), 'rack_3d_top', rel_dir='vision/rack_3d')
        side_rel, _, _ = image_io.save_image(np.fliplr(preview), 'rack_3d_side', rel_dir='vision/rack_3d')
        point_rel, _, _ = image_io.save_image(preview, 'rack_3d_pointcloud', rel_dir='vision/rack_3d')
        return {
            'front_view_url': settings.MEDIA_URL + front_rel,
            'top_view_url': settings.MEDIA_URL + top_rel,
            'side_view_url': settings.MEDIA_URL + side_rel,
            'pointcloud_view_url': settings.MEDIA_URL + point_rel,
        }

    def _output_from_points(self, *, points, recipe, rack_side, layer_no, roi_source, roi_id=None, token='') -> RackLocationOutput:
        actual_x, actual_y, actual_z = self.processor.calculate_median_xyz(points)
        confidence = min(0.99, max(0.0, points.shape[0] / 1000.0))
        frame = {
            'actual_x': actual_x,
            'actual_y': actual_y,
            'actual_z': actual_z,
            'confidence': confidence,
            'source': 'rack_3d_roi',
            'raw_data_path': token,
        }
        output = RackPoseEstimator(processor=self.processor).calculate_rack_offset(
            frame, recipe, rack_side=rack_side, layer_no=layer_no,
        )
        output.result_data = {
            **(output.result_data or {}),
            'roi_id': roi_id,
            'roi_source': roi_source,
            'coordinate_system': 'rack',
            'point_count': int(points.shape[0]),
        }
        return output

    def test_locate(self, *, token, roi_3d, recipe_id=None, rack_side=RackSide.LEFT, layer_no=1) -> dict:
        recipe = self._select_recipe(recipe_id=recipe_id, rack_side=rack_side, layer_no=layer_no)
        pointcloud = self._load_pointcloud(token)
        points = self.processor.crop_by_roi_3d(pointcloud, roi_3d)
        if points.shape[0] < self.processor.min_valid_points:
            raise ValueError('ROI 内有效点数太少')
        output = self._output_from_points(
            points=points,
            recipe=recipe,
            rack_side=rack_side,
            layer_no=int(layer_no),
            roi_source='request',
            token=token,
        )
        preview = image_io.pointcloud_to_preview(pointcloud)
        result_rel, _, _ = image_io.save_image(preview, 'rack_3d_cropped', rel_dir='vision/rack_3d')
        payload = output.to_payload()
        payload.update({
            'roi_source': 'request',
            'cropped_preview_url': settings.MEDIA_URL + result_rel,
        })
        return payload

    def locate(self, *, rack_side, layer_no, recipe_id=None, write_plc=False, product=None, rack=None, workflow=None):
        recipe = self._select_recipe(recipe_id=recipe_id, rack_side=rack_side, layer_no=layer_no)
        roi, roi_source = self._select_roi(recipe, int(layer_no))
        task = VisionTask.objects.create(
            task_type=VisionTaskType.RACK_LOCATING,
            product=product,
            rack=rack,
            status=ResultStatus.RUNNING,
            started_at=timezone.now(),
        )
        if roi is None:
            result = RackLocationResult.objects.create(
                vision_task=task,
                recipe=recipe,
                rack=rack,
                side=rack_side,
                position_no=recipe.position_no,
                layer_no=layer_no,
                confidence=0,
                is_success=False,
                error_code='ROI_NOT_CONFIGURED',
                error_message='未找到对应的三维 ROI 配方',
                result_data={'roi_source': roi_source, 'task_kind': 'RACK_3D_LOCATION'},
            )
            task.status = ResultStatus.FAILED
            task.finished_at = timezone.now()
            task.error_message = result.error_message
            task.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])
            return result

        captured = self.capture(recipe_id=recipe.id, rack_side=rack_side, layer_no=layer_no)
        pointcloud = self._load_pointcloud(captured['pointcloud_token'])
        points = self.processor.crop_by_roi_3d(pointcloud, roi3d_to_dict(roi))
        output = self._output_from_points(
            points=points,
            recipe=recipe,
            rack_side=rack_side,
            layer_no=int(layer_no),
            roi_source=roi_source,
            roi_id=roi.id,
            token=captured['pointcloud_token'],
        )
        payload = output.to_payload()
        result = RackLocationResult.objects.create(
            vision_task=task,
            recipe=recipe,
            rack=rack,
            side=rack_side,
            position_no=recipe.position_no,
            layer_no=layer_no,
            offset_x=_decimal(output.offset_x),
            offset_y=_decimal(output.offset_y),
            offset_z=_decimal(output.offset_z),
            offset_rz=_decimal(output.offset_rz),
            actual_x=_decimal(output.actual_x),
            actual_y=_decimal(output.actual_y),
            actual_z=_decimal(output.actual_z),
            confidence=_decimal(output.confidence, '0.0001'),
            is_recipe_matched=output.locate_ok,
            is_success=output.locate_ok,
            error_code=output.error_code,
            error_message=output.error_message,
            raw_data_path=captured['pointcloud_token'],
            result_data={
                **(payload.get('result_data') or {}),
                'task_kind': 'RACK_3D_LOCATION',
                'roi_id': roi.id,
                'roi_source': roi_source,
                'plc_payload': payload['plc_payload'],
            },
        )
        if write_plc:
            self.write_result_to_plc(result)
        task.status = ResultStatus.SUCCESS if result.is_success else ResultStatus.FAILED
        task.finished_at = timezone.now()
        task.error_message = result.error_message
        task.save(update_fields=['status', 'finished_at', 'error_message', 'updated_at'])
        return result

    def write_result_to_plc(self, result):
        return self.plc_writer.write(result)
```

- [ ] **Step 5: Run service tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DLocatorServiceTests -v 2
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add apps/vision/rack_location.py
git add -p apps/vision/tests.py
git commit -m "feat: add rack 3d locator service"
```

Expected: commit succeeds.

## Task 4: Formal `/api/vision/3d/...` APIs

**Files:**
- Modify: `apps/vision/tests.py`
- Modify: `apps/vision/views.py`
- Modify: `apps/vision/urls.py`

- [ ] **Step 1: Write failing API tests**

Add this test class after `Rack3DLocatorServiceTests`:

```python
@override_settings(MEDIA_ROOT=mkdtemp())
class Rack3DLocatorApiTests(TestCase):
    def setUp(self):
        Recipe = apps.get_model('vision', 'RackLocationRecipe')
        self.recipe = Recipe.objects.create(
            recipe_name='API-3D-LEFT-L1',
            rack_side='LEFT',
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

    def test_vision_3d_recipe_crud_uses_unified_response(self):
        create = self.client.post(
            reverse('vision:api_vision_3d_recipes'),
            data=json.dumps({
                'recipe_name': 'API-3D-RIGHT-L2',
                'rack_side': 'RIGHT',
                'rack_type': 'STD',
                'position_no': 2,
                'layer_no': 2,
                'layer_count': 3,
                'standard_x': 10,
                'standard_y': 20,
                'standard_z': 900,
                'hand_eye_config': {'matrix': 'identity'},
            }),
            content_type='application/json',
        )
        self.assertEqual(create.status_code, 200)
        created = create.json()
        self.assertTrue(created['success'])
        self.assertEqual(created['error'], '')
        recipe_id = created['data']['recipe']['id']

        detail = self.client.get(reverse('vision:api_vision_3d_recipe_detail', args=[recipe_id]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['data']['recipe']['rack_side'], 'RIGHT')

        update = self.client.put(
            reverse('vision:api_vision_3d_recipe_detail', args=[recipe_id]),
            data=json.dumps({'enabled': False, 'rack_type': 'UPDATED'}),
            content_type='application/json',
        )
        self.assertEqual(update.status_code, 200)
        self.assertFalse(update.json()['data']['recipe']['enabled'])

    def test_vision_3d_roi_crud(self):
        create = self.client.post(
            reverse('vision:api_vision_3d_rois'),
            data=json.dumps({
                'recipe_id': self.recipe.id,
                'roi_name': '第1层ROI',
                'mode': 'local',
                'layer_no': 1,
                'coordinate_system': 'rack',
                'x_min': -200,
                'x_max': 200,
                'y_min': -150,
                'y_max': 150,
                'z_min': 600,
                'z_max': 1200,
            }),
            content_type='application/json',
        )
        self.assertEqual(create.status_code, 200)
        roi_id = create.json()['data']['roi']['id']

        listing = self.client.get(reverse('vision:api_vision_3d_rois'), {'recipe_id': self.recipe.id})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()['data']['rois'][0]['id'], roi_id)

        update = self.client.put(
            reverse('vision:api_vision_3d_roi_detail', args=[roi_id]),
            data=json.dumps({'x_min': -180, 'x_max': 180}),
            content_type='application/json',
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.json()['data']['roi']['x_min'], -180.0)

    def test_vision_3d_capture_align_test_locate_and_write_plc(self):
        ROI = apps.get_model('vision', 'RackLocationROI3D')
        ROI.objects.create(
            recipe=self.recipe,
            roi_name='全局ROI',
            mode='global',
            x_min=-500,
            x_max=500,
            y_min=-300,
            y_max=300,
            z_min=500,
            z_max=1400,
        )

        capture = self.client.post(
            reverse('vision:api_vision_3d_capture'),
            data=json.dumps({'recipe_id': self.recipe.id, 'rack_side': 'LEFT', 'layer_no': 1}),
            content_type='application/json',
        )
        self.assertEqual(capture.status_code, 200)
        token = capture.json()['data']['pointcloud_token']

        align = self.client.post(
            reverse('vision:api_vision_3d_auto_align'),
            data=json.dumps({'pointcloud_token': token, 'recipe_id': self.recipe.id}),
            content_type='application/json',
        )
        self.assertEqual(align.status_code, 200)
        self.assertEqual(align.json()['data']['coordinate_system']['name'], 'rack')

        locate = self.client.post(
            reverse('vision:api_vision_3d_test_locate'),
            data=json.dumps({
                'pointcloud_token': token,
                'recipe_id': self.recipe.id,
                'rack_side': 'LEFT',
                'layer_no': 1,
                'roi': {
                    'x_min': -500,
                    'x_max': 500,
                    'y_min': -300,
                    'y_max': 300,
                    'z_min': 500,
                    'z_max': 1400,
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(locate.status_code, 200)
        self.assertIn('offset_x', locate.json()['data']['result'])

        result = self.client.post(
            reverse('vision:api_vision_3d_write_plc'),
            data=json.dumps({'result_id': 999999}),
            content_type='application/json',
        )
        self.assertEqual(result.status_code, 400)
        self.assertFalse(result.json()['success'])
        self.assertIn('error', result.json())
```

- [ ] **Step 2: Run API tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DLocatorApiTests -v 2
```

Expected: FAIL because new route names do not exist.

- [ ] **Step 3: Add JSON helpers and serializers**

In `apps/vision/views.py`, update model imports to include `RackLocationROI3D`:

```python
from .models import (
    CalibrationProfile,
    FoamInspectionResult,
    RackLocationROI3D,
    RackLocationRecipe,
    RackLocationResult,
    VisionImage,
    VisionRecipe,
    VisionTask,
)
```

Update rack_location imports:

```python
from .rack_location import (
    PlcVisionResultWriter,
    Rack3DLocator,
    RackLocationService,
    result_payload as rack_location_result_payload,
    roi3d_to_dict,
    sample_scene_median_xyz,
)
```

Add helpers near `_request_data()`:

```python
def _api3d_success(data=None, status=200):
    return JsonResponse({'success': True, 'data': data or {}, 'error': ''}, status=status)


def _api3d_error(message, status=400):
    return JsonResponse({'success': False, 'data': {}, 'error': str(message)}, status=status)


def _serialize_3d_recipe(recipe):
    return _serialize_rack_location_recipe(recipe)


def _serialize_3d_roi(roi):
    return roi3d_to_dict(roi)
```

- [ ] **Step 4: Add formal recipe and ROI views**

Add these views near existing rack-location API views:

```python
@require_http_methods(['GET', 'POST'])
def api_vision_3d_recipes(request):
    if request.method == 'GET':
        qs = RackLocationRecipe.objects.all().order_by('rack_side', 'position_no', 'layer_no')
        rack_side = request.GET.get('rack_side')
        layer_no = request.GET.get('layer_no')
        enabled = request.GET.get('enabled')
        if rack_side:
            qs = qs.filter(rack_side=rack_side)
        if layer_no not in (None, ''):
            qs = qs.filter(layer_no=int(layer_no))
        if enabled not in (None, ''):
            qs = qs.filter(enabled=_as_bool(enabled))
        return _api3d_success({'recipes': [_serialize_3d_recipe(recipe) for recipe in qs]})

    try:
        data = _request_data(request)
        recipe = RackLocationRecipe.objects.create(
            recipe_name=data.get('recipe_name') or f"3D-{data.get('rack_side', 'LEFT')}-L{data.get('layer_no', 1)}",
            rack_side=data.get('rack_side') or 'LEFT',
            rack_type=data.get('rack_type') or '',
            position_no=_as_int(data.get('position_no'), 1),
            layer_no=_as_int(data.get('layer_no'), 1),
            layer_count=_as_int(data.get('layer_count'), 3),
            standard_x=_as_float(data.get('standard_x'), 0),
            standard_y=_as_float(data.get('standard_y'), 0),
            standard_z=_as_float(data.get('standard_z'), 0),
            standard_rz=_as_float(data.get('standard_rz'), 0),
            hand_eye_config=data.get('hand_eye_config') or {'matrix': 'identity'},
            enabled=_as_bool(data.get('enabled'), True),
        )
        return _api3d_success({'recipe': _serialize_3d_recipe(recipe)})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_http_methods(['GET', 'PUT'])
def api_vision_3d_recipe_detail(request, recipe_id):
    recipe = get_object_or_404(RackLocationRecipe, pk=recipe_id)
    if request.method == 'GET':
        return _api3d_success({'recipe': _serialize_3d_recipe(recipe)})
    try:
        data = _request_data(request)
        for field in (
            'recipe_name', 'rack_side', 'rack_type', 'capture_pose_name',
            'standard_x', 'standard_y', 'standard_z', 'standard_rz',
            'hand_eye_config', 'enabled',
        ):
            if field in data:
                setattr(recipe, field, _as_bool(data[field]) if field == 'enabled' else data[field])
        for field in ('position_no', 'layer_no', 'layer_count'):
            if field in data:
                setattr(recipe, field, _as_int(data[field], getattr(recipe, field)))
        recipe.save()
        return _api3d_success({'recipe': _serialize_3d_recipe(recipe)})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_http_methods(['GET', 'POST'])
def api_vision_3d_rois(request):
    if request.method == 'GET':
        qs = RackLocationROI3D.objects.select_related('recipe').all()
        recipe_id = request.GET.get('recipe_id')
        if recipe_id not in (None, ''):
            qs = qs.filter(recipe_id=recipe_id)
        return _api3d_success({'rois': [_serialize_3d_roi(roi) for roi in qs.order_by('mode', 'layer_no')]})

    try:
        data = _request_data(request)
        roi = RackLocationROI3D.objects.create(
            recipe_id=data.get('recipe_id'),
            roi_name=data.get('roi_name') or '3D ROI',
            mode=data.get('mode') or RackLocationROI3D.MODE_LOCAL,
            layer_no=data.get('layer_no') or None,
            coordinate_system=data.get('coordinate_system') or 'rack',
            x_min=data.get('x_min'),
            x_max=data.get('x_max'),
            y_min=data.get('y_min'),
            y_max=data.get('y_max'),
            z_min=data.get('z_min'),
            z_max=data.get('z_max'),
            enabled=_as_bool(data.get('enabled'), True),
        )
        return _api3d_success({'roi': _serialize_3d_roi(roi)})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_http_methods(['PUT'])
def api_vision_3d_roi_detail(request, roi_id):
    try:
        roi = get_object_or_404(RackLocationROI3D, pk=roi_id)
        data = _request_data(request)
        for field in (
            'roi_name', 'mode', 'layer_no', 'coordinate_system',
            'x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max', 'enabled',
        ):
            if field in data:
                setattr(roi, field, _as_bool(data[field]) if field == 'enabled' else data[field])
        roi.save()
        return _api3d_success({'roi': _serialize_3d_roi(roi)})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)
```

- [ ] **Step 5: Add formal action views**

Add these views after the ROI views:

```python
@require_POST
def api_vision_3d_capture(request):
    try:
        data = _request_data(request)
        payload = Rack3DLocator().capture(
            recipe_id=data.get('recipe_id') or None,
            rack_side=data.get('rack_side') or 'LEFT',
            layer_no=_as_int(data.get('layer_no'), 1),
        )
        return _api3d_success(payload)
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_POST
def api_vision_3d_auto_align(request):
    try:
        data = _request_data(request)
        payload = Rack3DLocator().auto_align(
            token=data.get('pointcloud_token'),
            recipe_id=data.get('recipe_id') or None,
        )
        return _api3d_success(payload)
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_POST
def api_vision_3d_test_locate(request):
    try:
        data = _request_data(request)
        payload = Rack3DLocator().test_locate(
            token=data.get('pointcloud_token'),
            roi_3d=data.get('roi') or data.get('roi_3d') or {},
            recipe_id=data.get('recipe_id') or None,
            rack_side=data.get('rack_side') or 'LEFT',
            layer_no=_as_int(data.get('layer_no'), 1),
        )
        return _api3d_success({'result': payload})
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)


@require_POST
def api_vision_3d_write_plc(request):
    try:
        data = _request_data(request)
        result = get_object_or_404(RackLocationResult, pk=data.get('result_id'))
        response = Rack3DLocator().write_result_to_plc(result)
        result.refresh_from_db()
        return _api3d_success({
            'plc_response': response,
            'result': rack_location_result_payload(result),
        })
    except Exception as exc:  # noqa: BLE001
        return _api3d_error(exc)
```

- [ ] **Step 6: Add formal routes**

In `apps/vision/urls.py`, add these paths near the 3D rack API section:

```python
    path('api/vision/3d/recipes/', views.api_vision_3d_recipes, name='api_vision_3d_recipes'),
    path('api/vision/3d/recipes/<int:recipe_id>/', views.api_vision_3d_recipe_detail, name='api_vision_3d_recipe_detail'),
    path('api/vision/3d/rois/', views.api_vision_3d_rois, name='api_vision_3d_rois'),
    path('api/vision/3d/rois/<int:roi_id>/', views.api_vision_3d_roi_detail, name='api_vision_3d_roi_detail'),
    path('api/vision/3d/capture/', views.api_vision_3d_capture, name='api_vision_3d_capture'),
    path('api/vision/3d/auto-align/', views.api_vision_3d_auto_align, name='api_vision_3d_auto_align'),
    path('api/vision/3d/test-locate/', views.api_vision_3d_test_locate, name='api_vision_3d_test_locate'),
    path('api/vision/3d/write-plc/', views.api_vision_3d_write_plc, name='api_vision_3d_write_plc'),
```

- [ ] **Step 7: Run API tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.Rack3DLocatorApiTests -v 2
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

Run:

```powershell
git add apps/vision/views.py apps/vision/urls.py
git add -p apps/vision/tests.py
git commit -m "feat: expose vision 3d rack APIs"
```

Expected: commit succeeds.

## Task 5: Compatibility Delegation for Old Rack-Location Endpoints

**Files:**
- Modify: `apps/vision/tests.py`
- Modify: `apps/vision/rack_location.py`
- Modify: `apps/vision/views.py`

- [ ] **Step 1: Write failing compatibility tests**

Add these tests to `RackLocationWorkbenchTests`:

```python
    def test_old_workbench_calculate_accepts_3d_roi_payload(self):
        from unittest.mock import patch
        from apps.vision.rack_location import RackLocationService

        service = self._service()
        captured = service.capture_workbench(recipe_id=self.recipe.id)

        response = self.client.post(
            reverse('vision:api_rack_location_workbench_calculate'),
            data=json.dumps({
                'pointcloud_token': captured['pointcloud_token'],
                'roi_3d': {
                    'x_min': -500,
                    'x_max': 500,
                    'y_min': -300,
                    'y_max': 300,
                    'z_min': 500,
                    'z_max': 1400,
                },
                'recipe_id': self.recipe.id,
                'rack_side': 'LEFT',
                'layer_no': 1,
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['result']['roi_source'], 'request')
```

Add this test to `RackLocation3DViewTests`:

```python
    def test_old_trigger_endpoint_can_locate_with_3d_roi_recipe(self):
        ROI = apps.get_model('vision', 'RackLocationROI3D')
        ROI.objects.create(
            recipe=self.recipe,
            roi_name='兼容全局ROI',
            mode='global',
            x_min=-500,
            x_max=500,
            y_min=-300,
            y_max=300,
            z_min=500,
            z_max=1400,
        )

        response = self.client.post(
            reverse('vision:api_rack_location_trigger'),
            data={
                'position_no': 3,
                'layer_no': 1,
                'recipe_id': self.recipe.id,
                'rack_side': 'LEFT',
                'write_plc': 'false',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['result']['rack_side'], 'LEFT')
        self.assertIn('plc_payload', payload['result'])
```

- [ ] **Step 2: Run compatibility tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.RackLocationWorkbenchTests.test_old_workbench_calculate_accepts_3d_roi_payload apps.vision.tests.RackLocation3DViewTests.test_old_trigger_endpoint_can_locate_with_3d_roi_recipe -v 2
```

Expected: FAIL because old views ignore `roi_3d` and old trigger hard-codes `BOTH`.

- [ ] **Step 3: Update `RackLocationService.calculate_workbench()` to accept 3D ROI**

In `apps/vision/rack_location.py`, modify `RackLocationService.calculate_workbench()` at the top:

```python
    def calculate_workbench(self, *, token, roi_config, recipe_id=None,
                            recipe_data=None, layer_no=1, roi_3d=None, rack_side=RackSide.LEFT) -> dict:
        if roi_3d:
            return Rack3DLocator(
                frame_provider=self.frame_provider,
                plc_writer=self.plc_writer,
            ).test_locate(
                token=token,
                roi_3d=roi_3d,
                recipe_id=recipe_id,
                rack_side=rack_side,
                layer_no=layer_no,
            )
        recipe = self._build_workbench_recipe(recipe_id, recipe_data)
```

Keep the existing 2D `target_roi` branch unchanged after this insertion.

- [ ] **Step 4: Update old calculate view to pass 3D ROI**

In `apps/vision/views.py`, modify `api_rack_location_workbench_calculate()`:

```python
        payload = RackLocationService().calculate_workbench(
            token=data.get('pointcloud_token'),
            roi_config=data.get('roi_config') or {},
            recipe_id=data.get('recipe_id') or None,
            recipe_data=data.get('recipe_data') or None,
            layer_no=_as_int(data.get('layer_no'), 1),
            roi_3d=data.get('roi_3d') or data.get('roi'),
            rack_side=data.get('rack_side') or 'LEFT',
        )
```

- [ ] **Step 5: Update old trigger view to delegate when 3D ROI exists**

In `apps/vision/views.py`, modify `api_rack_location_trigger()`:

```python
        rack_side = data.get('rack_side') or 'BOTH'
        if data.get('rack_side') or data.get('use_3d_roi'):
            result = Rack3DLocator().locate(
                rack_side=rack_side,
                layer_no=layer_no,
                recipe_id=recipe_id,
                write_plc=write_plc,
            )
        else:
            result = RackLocationService().trigger(
                position_no=position_no,
                layer_no=layer_no,
                recipe_id=recipe_id,
                rack_side='BOTH',
                write_plc=write_plc,
            )
```

- [ ] **Step 6: Run compatibility tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.RackLocationWorkbenchTests.test_old_workbench_calculate_accepts_3d_roi_payload apps.vision.tests.RackLocation3DViewTests.test_old_trigger_endpoint_can_locate_with_3d_roi_recipe -v 2
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

Run:

```powershell
git add apps/vision/rack_location.py apps/vision/views.py
git add -p apps/vision/tests.py
git commit -m "feat: keep rack location endpoints compatible"
```

Expected: commit succeeds.

## Task 6: Workbench UI for 3D ROI Parameters

**Files:**
- Modify: `apps/vision/tests.py`
- Modify: `templates/vision/rack_locator_panel.html`
- Modify: `static/vision/js/rack_locator_workbench.js`

- [ ] **Step 1: Replace outdated template expectation with failing new UI test**

In `RackLocation3DViewTests`, replace `test_existing_rack_locator_panel_focuses_on_position_and_layer_not_left_right_side` with:

```python
    def test_rack_locator_panel_exposes_3d_roi_workbench_controls(self):
        response = self.client.get(reverse('vision:rack_locator_panel'))

        self.assertContains(response, '3D 料架定位工作台')
        self.assertContains(response, 'rack-side')
        self.assertContains(response, '左料架')
        self.assertContains(response, '右料架')
        self.assertContains(response, 'locate-mode')
        self.assertContains(response, 'roi-x-min')
        self.assertContains(response, 'roi-x-max')
        self.assertContains(response, 'roi-y-min')
        self.assertContains(response, 'roi-y-max')
        self.assertContains(response, 'roi-z-min')
        self.assertContains(response, 'roi-z-max')
        self.assertContains(response, 'btn-auto-align')
        self.assertContains(response, 'btn-save-roi')
        self.assertContains(response, 'btn-write-plc')
        self.assertContains(response, 'api_vision_3d_capture')
        self.assertContains(response, 'api_vision_3d_test_locate')
```

- [ ] **Step 2: Run template test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.RackLocation3DViewTests.test_rack_locator_panel_exposes_3d_roi_workbench_controls -v 2
```

Expected: FAIL because the page does not yet expose all 3D ROI controls and new route names.

- [ ] **Step 3: Add controls to the workbench template**

In `templates/vision/rack_locator_panel.html`, add this block in the right/result panel before the result display:

```html
<div class="rl-field-grid">
  <label>料架侧别
    <select id="rack-side">
      <option value="LEFT">左料架</option>
      <option value="RIGHT">右料架</option>
    </select>
  </label>
  <label>定位模式
    <select id="locate-mode">
      <option value="global">全局定位</option>
      <option value="local" selected>局部定位</option>
    </select>
  </label>
  <label>层号
    <select id="layer-no-select">
      <option value="1">第 1 层</option>
      <option value="2">第 2 层</option>
      <option value="3">第 3 层</option>
    </select>
  </label>
</div>

<div class="rl-roi3d-panel">
  <h3>三维 ROI 参数</h3>
  <div class="rl-roi3d-grid">
    <label>X_min<input id="roi-x-min" type="number" step="0.001" value="-500"></label>
    <label>X_max<input id="roi-x-max" type="number" step="0.001" value="500"></label>
    <label>Y_min<input id="roi-y-min" type="number" step="0.001" value="-300"></label>
    <label>Y_max<input id="roi-y-max" type="number" step="0.001" value="300"></label>
    <label>Z_min<input id="roi-z-min" type="number" step="0.001" value="500"></label>
    <label>Z_max<input id="roi-z-max" type="number" step="0.001" value="1400"></label>
  </div>
</div>
```

Add action buttons near existing workbench actions:

```html
<button id="btn-auto-align" class="btn btn-secondary">自动识别料架姿态</button>
<button id="btn-save-roi" class="btn btn-secondary">保存 ROI 配方</button>
<button id="btn-write-plc" class="btn btn-secondary">写入 PLC</button>
```

Update `window.rackLocatorConfig`:

```javascript
window.rackLocatorConfig = {
  captureUrl: '{% url "vision:api_vision_3d_capture" %}',
  autoAlignUrl: '{% url "vision:api_vision_3d_auto_align" %}',
  testLocateUrl: '{% url "vision:api_vision_3d_test_locate" %}',
  saveRoiUrl: '{% url "vision:api_vision_3d_rois" %}',
  writePlcUrl: '{% url "vision:api_vision_3d_write_plc" %}',
  legacyCaptureUrl: '{% url "vision:api_rack_location_workbench_capture" %}',
  legacyCalculateUrl: '{% url "vision:api_rack_location_workbench_calculate" %}',
  legacySaveUrl: '{% url "vision:api_rack_location_workbench_save" %}',
  triggerUrl: '{% url "vision:api_rack_location_trigger" %}',
  resultsUrl: '{% url "vision:api_rack_location_results" %}',
};
```

- [ ] **Step 4: Update JavaScript to use 3D ROI**

In `static/vision/js/rack_locator_workbench.js`, add helpers near `currentRecipeData()`:

```javascript
  function numberInput(id, fallback) {
    const node = $(id);
    const value = Number(node?.value);
    return Number.isFinite(value) ? value : fallback;
  }

  function currentRackSide() {
    return $('rack-side')?.value || 'LEFT';
  }

  function currentLayerNo() {
    return Number($('layer-no-select')?.value || $('layer-no')?.value || 1);
  }

  function currentMode() {
    return $('locate-mode')?.value || 'local';
  }

  function currentRoi3D() {
    return {
      x_min: numberInput('roi-x-min', -500),
      x_max: numberInput('roi-x-max', 500),
      y_min: numberInput('roi-y-min', -300),
      y_max: numberInput('roi-y-max', 300),
      z_min: numberInput('roi-z-min', 500),
      z_max: numberInput('roi-z-max', 1400),
    };
  }
```

Modify capture click body:

```javascript
      const data = await postJson(CFG.captureUrl, {
        recipe_id: $('recipe-id').value || null,
        rack_side: currentRackSide(),
        layer_no: currentLayerNo(),
      });
      const payload = data.data || data;
      if (!data.success) { setStatus(data.error || '采集失败'); return; }
      state.token = payload.pointcloud_token;
      image.src = (payload.pointcloud_preview_url || payload.preview_image_url) + '?t=' + Date.now();
      image.dataset.naturalWidth = payload.image_width;
      image.dataset.naturalHeight = payload.image_height;
      $('rl-source').textContent = '数据源 ' + (payload.source || '—');
```

Add auto-align handler:

```javascript
  $('btn-auto-align')?.addEventListener('click', async () => {
    if (!state.token) { setStatus('请先采集 3D 图像。'); return; }
    showLoading('识别料架姿态中...');
    try {
      const data = await postJson(CFG.autoAlignUrl, {
        pointcloud_token: state.token,
        recipe_id: $('recipe-id').value || null,
      });
      if (!data.success) { setStatus(data.error || '姿态识别失败'); return; }
      setStatus('料架姿态识别完成，可配置三维 ROI。');
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); }
  });
```

Modify calculate click to call `testLocateUrl`:

```javascript
      const data = await postJson(CFG.testLocateUrl, {
        pointcloud_token: state.token,
        recipe_id: $('recipe-id').value || null,
        rack_side: currentRackSide(),
        layer_no: currentLayerNo(),
        roi: currentRoi3D(),
      });
      if (!data.success) { setStatus(data.error || '计算失败'); return; }
      renderResult(data.data.result);
```

Add save ROI handler:

```javascript
  $('btn-save-roi')?.addEventListener('click', async () => {
    showLoading('保存 ROI 配方中...');
    try {
      const mode = currentMode();
      const body = {
        recipe_id: $('recipe-id').value || null,
        roi_name: mode === 'global' ? '全局ROI' : `第${currentLayerNo()}层ROI`,
        mode,
        layer_no: mode === 'global' ? null : currentLayerNo(),
        coordinate_system: 'rack',
        ...currentRoi3D(),
      };
      const data = await postJson(CFG.saveRoiUrl, body);
      if (!data.success) { setStatus(data.error || '保存 ROI 失败'); return; }
      setStatus('ROI 配方已保存。');
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); }
  });
```

Add write PLC handler:

```javascript
  $('btn-write-plc')?.addEventListener('click', async () => {
    const resultId = state.lastResultId;
    if (!resultId) { setStatus('请先保存或选择一条定位结果。'); return; }
    showLoading('写入 PLC 中...');
    try {
      const data = await postJson(CFG.writePlcUrl, { result_id: resultId });
      if (!data.success) { setStatus(data.error || 'PLC 写入失败'); return; }
      setStatus('PLC 写入完成。');
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); }
  });
```

In `renderResult(r)`, add:

```javascript
    state.lastResultId = r.id || r.result_id || state.lastResultId || null;
```

- [ ] **Step 5: Run template test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.RackLocation3DViewTests.test_rack_locator_panel_exposes_3d_roi_workbench_controls -v 2
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

Run:

```powershell
git add templates/vision/rack_locator_panel.html static/vision/js/rack_locator_workbench.js
git add -p apps/vision/tests.py
git commit -m "feat: add 3d ROI workbench controls"
```

Expected: commit succeeds.

## Task 7: Regression and Migration Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run focused 3D tests**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision.tests.RackLocationROI3DModelTests apps.vision.tests.RackLocationPointCloudProcessorTests apps.vision.tests.Rack3DLocatorServiceTests apps.vision.tests.Rack3DLocatorApiTests apps.vision.tests.RackLocationService3DTests apps.vision.tests.RackLocation3DViewTests apps.vision.tests.RackLocationWorkbenchTests -v 2
```

Expected: PASS.

- [ ] **Step 2: Run app test suite**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.vision -v 2
```

Expected: PASS.

- [ ] **Step 3: Run Django system checks and migration check**

Run:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Expected: PASS and no model changes detected.

- [ ] **Step 4: Inspect final diff**

Run:

```powershell
git status --short
git diff --stat
```

Expected: only intentional files are modified, or the working tree is clean after commits.

- [ ] **Step 5: Commit any final verification-only adjustments**

If fixes were required during regression, commit them:

```powershell
git add apps/vision/models.py apps/vision/admin.py apps/vision/rack_location.py apps/vision/views.py apps/vision/urls.py templates/vision/rack_locator_panel.html static/vision/js/rack_locator_workbench.js apps/vision/migrations/0007_racklocationroi3d.py
git add -p apps/vision/tests.py
git commit -m "test: verify 3d rack location refactor"
```

Expected: commit succeeds only if there were additional fixes.

## Self-Review

Spec coverage:

- `RackLocationROI3D` model and migration: Task 1.
- 3D ROI point-cloud cropping: Task 2.
- `Rack3DLocator` facade, capture, auto-align, corrected views, test-locate, locate, PLC writer boundary: Task 3.
- Formal `/api/vision/3d/...` APIs: Task 4.
- Old `api/rack-location/...` compatibility: Task 5.
- Workbench controls for rack side, mode, layer, six ROI numbers, actions, and results: Task 6.
- Verification and regression: Task 7.

Unresolved-marker scan:

- The plan contains concrete class names, method names, fields, routes, test names, commands, and expected outcomes.
- No unresolved requirement markers are present.

Type consistency:

- Model name: `RackLocationROI3D`.
- Service name: `Rack3DLocator`.
- ROI keys: `x_min`, `x_max`, `y_min`, `y_max`, `z_min`, `z_max`.
- Route names: `api_vision_3d_recipes`, `api_vision_3d_recipe_detail`, `api_vision_3d_rois`, `api_vision_3d_roi_detail`, `api_vision_3d_capture`, `api_vision_3d_auto_align`, `api_vision_3d_test_locate`, `api_vision_3d_write_plc`.
