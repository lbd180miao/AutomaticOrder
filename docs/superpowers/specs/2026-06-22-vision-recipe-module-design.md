# Vision Recipe Module Design

## Goal

Add a visual recipe module under the existing vision system without changing the global navigation or disrupting the current foam inspection workbench layout.

## Business logic

The 2D foam recipe maps the current POS/layer to a pair of detection ROIs: leftFoamROI and rightFoamROI.

During inspection, the system chooses the recipe in this order:

- A manually selected recipe for the current one-shot inspection.
- The active FOAM_2D recipe matching the current POS.
- Existing calibration/default inspection configuration when no recipe exists.

Manual selection is cleared immediately after one inspection so later inspections return to POS-based automatic matching.

## Architecture

The module uses a lightweight VisionRecipe Django model. FOAM_2D is implemented now; RACK_3D is reserved through the same model and a frontend tab placeholder.

The existing FoamInspector already accepts side-specific ROI config through inspection_config["foam_rois"]. Recipe pixel ROIs are converted into the ratio format expected by FoamInspector, so the core algorithm does not need a rewrite.

## Backend changes

- apps/vision/models.py: add VisionRecipe.
- apps/vision/migrations/0004_visionrecipe.py: create the database table.
- apps/vision/admin.py: register VisionRecipe.
- apps/vision/recipe_utils.py: add default recipe creation, serialization, validation, recipe lookup, and recipe-to-inspection-config conversion helpers.
- apps/vision/views.py: add recipe APIs and extend foam inspect APIs to pass recipe options.
- apps/vision/urls.py: add /vision/api/recipes/... routes.
- apps/vision/services.py: extend inspect_foam() with optional recipe_id and use_recipe parameters.

## API design

- GET /vision/api/recipes/: list recipes with optional filters.
- GET /vision/api/recipes/foam-2d/by-pos/?pos=0: return the active FOAM_2D recipe for one POS, creating defaults if missing.
- POST /vision/api/recipes/foam-2d/save/: create or update a FOAM_2D recipe for exactly one POS.
- POST /vision/api/recipes/foam-2d/defaults/: ensure default POS 0/1/2 recipes exist.

Existing inspection APIs accept position_index, optional recipe_id, and use_recipe. If no recipe is found, inspection falls back to the current calibration/default path.

## Frontend design

The foam workbench keeps the existing two-column layout. A new “配方管理” button opens a right-side drawer.

The drawer contains:

- “泡棉检测配方（2D）” tab with POS 0/1/2 recipe cards.
- “料架定位配方（3D）” tab with a later-development placeholder.
- ROI and threshold form controls for the selected 2D recipe.
- Save, reset-default, cancel, and one-shot manual-use actions.

Current POS remains sourced from the existing #pos-index input.

## ROI rendering

The existing preview ROI overlay is reused. Recipe pixel ROIs are converted to ratios for display. The backend result image already draws side ROIs when FoamInspector receives foam_rois; the frontend also displays the current recipe name and POS in the result detail area.

## Safety constraints

- Do not change top navigation or base layout.
- Do not remove existing CalibrationProfile APIs.
- Do not rewrite FoamInspector detection logic.
- Existing callers of VisionService.inspect_foam() must continue working without recipe parameters.
- Missing recipes must not crash inspection.
- Saving one POS recipe must not overwrite other POS recipes.

## Acceptance checks

- The workbench has a recipe management entry.
- The drawer shows 2D and 3D tabs.
- The 3D tab is a placeholder.
- POS 0/1/2 default 2D recipes exist.
- POS changes highlight and display the matching recipe.
- Inspection requests include recipe_id when available.
- Detection result returns recipe information.
- Manual recipe selection affects one inspection only.
- Existing layout and old inspection behavior remain available.
