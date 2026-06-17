# Foam ROI Capture Design

## Goal

Add a manual front-end trigger on `/vision/tasks/` for a 2D fixed camera foam inspection. One click represents a PLC sequence trigger: capture one image, analyze the ROI area, save the original/result images, and show the new task detail.

## Design

The existing `VisionService.inspect_foam()` already creates a `VisionTask`, runs the 2D foam inspector, stores the ROI-annotated result image, and persists `FoamInspectionResult`. The UI will reuse that service rather than adding a new algorithm path.

The task list page gets a compact POST form with a PLC sequence input. The new view validates `position_index` as a non-negative integer, calls `VisionService.inspect_foam(product=None, rack=None, position_index=position_index)`, adds a status message, and redirects to the created task detail page.

## Files

- `apps/vision/tests.py`: view tests for the toolbar button and POST behavior.
- `apps/vision/views.py`: POST handler for manual capture.
- `apps/vision/urls.py`: route for the capture action.
- `templates/vision/task_list.html`: toolbar form and button.
- `static/css/app.css`: small input width helper for the PLC sequence field.

## Verification

Run `.\.venv\Scripts\python.exe manage.py test apps.vision` and `.\.venv\Scripts\python.exe manage.py check`.
