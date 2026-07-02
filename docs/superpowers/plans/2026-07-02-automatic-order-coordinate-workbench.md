# AutomaticOrder Coordinate Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a top-level coordinate module to AutomaticOrder that edits and persists the three-layer hand-eye coordinate chain and previews the requested deterministic camera point cloud.

**Architecture:** Create `apps.coordinates` as an orchestration/UI module without duplicating calibration or recipe models. It writes `T_flange_camera` through the linked `HandEyeCalibration` when present or the existing `RackLocationRecipe.hand_eye_config` fallback, writes each layer pose to `capture_pose`, and reuses `CoordinateTransformService` for `P_base = T_base_flange × T_flange_camera × P_camera`.

**Tech Stack:** Django 6, NumPy/SciPy, Django templates, native JavaScript and Canvas.

---

### Task 1: App shell and top-level navigation

**Files:**
- Create: `apps/coordinates/__init__.py`
- Create: `apps/coordinates/apps.py`
- Create: `apps/coordinates/urls.py`
- Create: `apps/coordinates/views.py`
- Create: `apps/coordinates/tests/__init__.py`
- Create: `apps/coordinates/tests/test_views.py`
- Modify: `AutomaticOrder/settings.py`
- Modify: `AutomaticOrder/urls.py`
- Modify: `templates/base.html`

- [ ] Write a failing test asserting `/coordinates/` returns 200, contains “坐标模块”, and the top bar has “坐标” immediately after “视觉”.
- [ ] Run `python manage.py test apps.coordinates.tests.test_views -v 2` and confirm the route/module failure.
- [ ] Register `apps.coordinates`, mount `/coordinates/`, add the peer navigation link, and render the workbench template.
- [ ] Re-run the test and commit `feat: add coordinate module shell`.

### Task 2: Existing-model persistence and requested coordinate chain

**Files:**
- Create: `apps/coordinates/services.py`
- Create: `apps/coordinates/tests/test_services.py`

- [ ] Write failing tests for these exact behaviors:
  - requested matrix transforms camera point `[0,0,800]` at layer 2 to `[1030,440,1820]`;
  - deterministic cloud has X in `[-200,200]`, Y in `[-100,100]`, support Z in `[800,820]`;
  - three default poses use Z `600/900/1200`;
  - save persists hand-eye data, capture pose, theoretical XYZ, and robot-coordinate ROI to existing `RackLocationRecipe` fields;
  - preview never writes the database.
- [ ] Run `python manage.py test apps.coordinates.tests.test_services -v 2` and confirm the service import failure.
- [ ] Implement `CoordinateWorkbenchService` with deterministic simulation, `CoordinateTransformService`, closed-boundary ROI crop, median actual values, offsets `actual - theoretical`, and transaction-safe save.
- [ ] Re-run tests and commit `feat: add coordinate workbench service`.

### Task 3: JSON API contracts

**Files:**
- Modify: `apps/coordinates/views.py`
- Modify: `apps/coordinates/urls.py`
- Create: `apps/coordinates/tests/test_api.py`

- [ ] Write failing tests for GET workbench, POST draft preview, POST save/reload, invalid rigid matrix 400, empty ROI 422, and missing layer recipe 404.
- [ ] Run `python manage.py test apps.coordinates.tests.test_api -v 2` and confirm endpoint failures.
- [ ] Implement `{success,data,error}` JSON responses, JSON parsing, stable error codes, CSRF-protected POST endpoints, and no silent REAL-to-MOCK fallback.
- [ ] Re-run tests and commit `feat: expose coordinate module api`.

### Task 4: Workbench page and interaction

**Files:**
- Create: `templates/coordinates/workbench.html`
- Create: `static/coordinates/workbench.css`
- Create: `static/coordinates/workbench.js`
- Modify: `apps/coordinates/tests/test_views.py`

- [ ] Extend the failing page test for layer selector, 4×4 matrix editor, six-axis pose, theoretical XYZ, robot ROI, Preview/Save/Restore actions, three Canvas clouds, result cards, and a hand-eye calibration link.
- [ ] Build the responsive workbench in the existing AutomaticOrder visual language.
- [ ] Implement draft state, dirty guard, XY/XZ Canvas projections, preview/save/restore, server field errors, and current layer switching.
- [ ] Run coordinate page/API tests and commit `feat: add coordinate engineering workbench`.

### Task 5: Verification on the real 8083 surface

**Files:**
- Modify only files required by failing coordinate tests or browser acceptance.

- [ ] Run `python manage.py test apps.coordinates apps.vision.rack_3d.tests -v 1`.
- [ ] Run `python manage.py check` and `python manage.py makemigrations --check --dry-run`.
- [ ] Start the isolated worktree server, open `/vision/tasks/`, and confirm “坐标” appears after “视觉”.
- [ ] Open `/coordinates/`; verify all three layers, layer-2 support at base Z `1820–1840`, preview-only drafts, persisted saves, invalid matrix rejection, restore, and XY/XZ projection.
- [ ] Integrate the branch without overwriting the user's uncommitted 3D recipe work, restart port 8083, and repeat the navigation/page checks.

