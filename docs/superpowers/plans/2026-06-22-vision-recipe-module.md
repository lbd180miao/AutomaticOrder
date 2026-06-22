# Vision Recipe Module Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

Goal: Build the 2D foam visual recipe module and reserve the 3D recipe entry without disrupting the existing foam inspection workbench.

Architecture: Add a VisionRecipe model and helper utilities that convert recipe ROI JSON into the existing FoamInspector configuration format. Extend existing inspection APIs compatibly, then add a right-side recipe drawer to the Django template.

Tech Stack: Django, SQLite, Django templates, vanilla JavaScript, OpenCV-backed existing FoamInspector, Django TestCase.

---

## File Structure

- Create apps/vision/recipe_utils.py: default recipes, validation, serialization, ROI conversion, recipe lookup.
- Modify apps/vision/models.py: add VisionRecipe.
- Create apps/vision/migrations/0004_visionrecipe.py: schema migration.
- Modify apps/vision/admin.py: register VisionRecipe.
- Modify apps/vision/services.py: accept optional recipe arguments and enrich result data.
- Modify apps/vision/views.py: add recipe APIs and pass recipe data to inspection.
- Modify apps/vision/urls.py: expose recipe APIs.
- Modify templates/vision/foam_inspector_interactive.html: add recipe drawer and frontend state.
- Modify apps/vision/tests.py: cover recipe model/API/service/template behavior.

## Task 1: Backend recipe model and utilities

Files: apps/vision/models.py, apps/vision/migrations/0004_visionrecipe.py, apps/vision/recipe_utils.py, apps/vision/admin.py, apps/vision/tests.py.

- [ ] Step 1: Write failing tests for default recipe creation, serialization, validation, and config conversion.
- [ ] Step 2: Run python manage.py test apps.vision.tests.VisionRecipeModelTests -v 2 and confirm it fails because recipe code is missing.
- [ ] Step 3: Implement the model, migration, admin registration, and helper functions.
- [ ] Step 4: Run python manage.py test apps.vision.tests.VisionRecipeModelTests -v 2 and confirm it passes.

## Task 2: Service recipe integration

Files: apps/vision/services.py, apps/vision/tests.py.

- [ ] Step 1: Write failing tests for explicit recipe_id, POS fallback, recipe metadata recording, and no-recipe fallback.
- [ ] Step 2: Run python manage.py test apps.vision.tests.VisionRecipeServiceTests -v 2 and confirm it fails.
- [ ] Step 3: Extend inspect_foam() with recipe_id=None and use_recipe=True, merge recipe config, and enrich result data.
- [ ] Step 4: Run python manage.py test apps.vision.tests.VisionRecipeServiceTests -v 2 and confirm it passes.

## Task 3: Recipe APIs and inspection API request/response

Files: apps/vision/views.py, apps/vision/urls.py, apps/vision/tests.py.

- [ ] Step 1: Write failing tests for recipe list, by-POS lookup, save, default initialization, capture inspect recipe_id, and upload inspect recipe_id.
- [ ] Step 2: Run python manage.py test apps.vision.tests.VisionRecipeApiTests -v 2 and confirm it fails.
- [ ] Step 3: Add recipe routes, JSON views, and compatible inspection request parsing.
- [ ] Step 4: Run python manage.py test apps.vision.tests.VisionRecipeApiTests -v 2 and confirm it passes.

## Task 4: Frontend recipe drawer

Files: templates/vision/foam_inspector_interactive.html, apps/vision/tests.py.

- [ ] Step 1: Write a failing template test asserting the workbench exposes recipe drawer controls, tabs, API URLs, and recipe state names.
- [ ] Step 2: Run python manage.py test apps.vision.tests.VisionRecipeWorkbenchTemplateTests -v 2 and confirm it fails.
- [ ] Step 3: Add the “配方管理” button, drawer, tabs, recipe card rendering, ROI form, POS synchronization, one-shot manual selection, and request payload integration.
- [ ] Step 4: Run python manage.py test apps.vision.tests.VisionRecipeWorkbenchTemplateTests -v 2 and confirm it passes.

## Task 5: Full regression verification

- [ ] Run python manage.py test apps.vision -v 2.
- [ ] Run python manage.py check.
- [ ] Inspect git diff -- apps/vision templates/vision docs/superpowers.

## Self-review

- Spec coverage: model, API, service integration, drawer UI, manual one-shot recipe, ROI display, fallback behavior, and regression testing are covered.
- Placeholder scan: no TBD/TODO placeholders are used.
- Type consistency: backend uses VisionRecipe, recipe_type, roi_config, threshold_config, recipe_id, and use_recipe consistently.
