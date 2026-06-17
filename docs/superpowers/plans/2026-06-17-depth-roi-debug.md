# Depth ROI Debug Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a depth-camera ROI debug button to vision task detail pages.

**Architecture:** Add a POST-only Django view that creates reusable debug rack data, calls `VisionService.locate_both_racks()`, then redirects to the generated depth-camera task. Add the form to `templates/vision/task_detail.html`.

**Tech Stack:** Django views, Django templates, Django TestCase, existing vision service and rack locator.

---

### Task 1: Failing View Tests

**Files:**
- Modify: `apps/vision/tests.py`

- [ ] **Step 1: Add tests**

Add one test that verifies the detail page renders a form posting to `vision:capture_depth_roi`, and one POST test that verifies a `RACK_LOCATING` task and two `RackLocationResult` records are created before redirecting to the new task detail.

- [ ] **Step 2: Run tests**

Run: `.\.venv\Scripts\python.exe manage.py test apps.vision`

Expected: fail because `vision:capture_depth_roi` is not registered.

### Task 2: POST View and URL

**Files:**
- Modify: `apps/vision/views.py`
- Modify: `apps/vision/urls.py`

- [ ] **Step 1: Add helper**

Create `_get_depth_roi_debug_context()` that returns a debug `Rack` and `RackRecipe`.

- [ ] **Step 2: Add POST view**

Create `capture_depth_roi(request, pk)` that loads the source task, runs `VisionService().locate_both_racks(product=None, rack=rack, recipe=recipe)`, adds a message, and redirects to the new task.

- [ ] **Step 3: Register URL**

Add `path('tasks/<int:pk>/capture-depth-roi/', views.capture_depth_roi, name='capture_depth_roi')`.

### Task 3: Detail Page Button

**Files:**
- Modify: `templates/vision/task_detail.html`

- [ ] **Step 1: Add button**

Add a CSRF-protected form in the page header with submit text `深度相机拍照检测ROI`.

- [ ] **Step 2: Verify**

Run `.\.venv\Scripts\python.exe manage.py test apps.vision` and `.\.venv\Scripts\python.exe manage.py check`.
