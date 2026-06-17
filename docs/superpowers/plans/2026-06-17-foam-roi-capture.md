# Foam ROI Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manual 2D camera ROI capture button to the vision task list.

**Architecture:** Reuse `VisionService.inspect_foam()` as the single capture/analyze/persist path. Add a POST-only Django view that accepts a PLC sequence number as `position_index`, then redirects to the generated task detail page.

**Tech Stack:** Django views, Django templates, Django TestCase, existing OpenCV-backed vision service.

---

### Task 1: View Tests

**Files:**
- Modify: `apps/vision/tests.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert the task list renders a POST form targeting `vision:capture_foam_roi`, and that posting `plc_sequence=3` creates a foam inspection result with `position_index == 3` and redirects to the task detail page.

- [ ] **Step 2: Run the focused test**

Run: `.\.venv\Scripts\python.exe manage.py test apps.vision`

Expected: FAIL because `vision:capture_foam_roi` does not exist yet.

### Task 2: Capture View and URL

**Files:**
- Modify: `apps/vision/views.py`
- Modify: `apps/vision/urls.py`

- [ ] **Step 1: Implement the POST handler**

Create `capture_foam_roi(request)` that rejects non-POST requests, parses `plc_sequence`, calls `VisionService().inspect_foam(...)`, and redirects to `vision:task_detail`.

- [ ] **Step 2: Register the route**

Add `path('tasks/capture-foam-roi/', views.capture_foam_roi, name='capture_foam_roi')`.

- [ ] **Step 3: Run tests**

Run: `.\.venv\Scripts\python.exe manage.py test apps.vision`

Expected: template test still fails until the button exists.

### Task 3: Template Button

**Files:**
- Modify: `templates/vision/task_list.html`
- Modify: `static/css/app.css`

- [ ] **Step 1: Add toolbar form**

Add a CSRF-protected inline form with a numeric PLC sequence input and a submit button labeled `2D相机拍照检测ROI`.

- [ ] **Step 2: Add small CSS helper**

Add a class for the sequence input so it stays compact in the toolbar.

- [ ] **Step 3: Verify**

Run: `.\.venv\Scripts\python.exe manage.py test apps.vision`
Run: `.\.venv\Scripts\python.exe manage.py check`

Expected: both commands exit with code 0.
