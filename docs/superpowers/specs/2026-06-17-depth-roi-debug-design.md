# Depth ROI Debug Design

## Goal

Add a manual depth-camera ROI debug trigger on vision task detail pages. The button should let an operator capture one simulated depth-camera frame, run the rack ROI location algorithm, and open the generated task detail page.

## Design

The project already has a depth-camera path in `VisionService.locate_both_racks()`. The debug trigger reuses that service so the displayed result image contains the existing ROI overlays: pillar baseline ROI, boxing-area ROI, and compensation arrows.

The detail page gets a POST form button labeled `深度相机拍照检测ROI`. The POST view creates or reuses debug data:

- Rack recipe: `DEBUG-DEPTH-ROI`
- Rack: `DEBUG-RACK`

It then calls `VisionService.locate_both_racks(product=None, rack=debug_rack, recipe=debug_recipe)`. The service creates one `VisionTask`, two rack-side results, and the original/result images. The view redirects to the new task detail page.

## Verification

Run `.\.venv\Scripts\python.exe manage.py test apps.vision` and `.\.venv\Scripts\python.exe manage.py check`.
