# Technical Design Document

## System Overview

视觉配方模块优化系统采用 Django 后端 + 原生 JavaScript 前端架构，实现泡棉检测工作台与配方管理模块的数据互通。

### Architecture Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Browser)                      │
├─────────────────────────────────────────────────────────────┤
│  foam_inspector_interactive.html                            │
│  ├─ Recipe State Manager (JS)                               │
│  ├─ Recipe Card Renderer                                    │
│  ├─ ROI Visualizer (Canvas)                                 │
│  └─ POS Selector Dialog                                     │
└─────────────────────────────────────────────────────────────┘
                           ↕ HTTP/JSON
┌─────────────────────────────────────────────────────────────┐
│                      Backend (Django)                       │
├─────────────────────────────────────────────────────────────┤
│  apps/vision/views.py                                       │
│  ├─ api_vision_recipes (GET)                                │
│  ├─ api_foam_recipe_by_pos (GET)                            │
│  ├─ api_foam_recipe_save (POST)                             │
│  ├─ api_foam_capture_inspect (POST) + recipe_id            │
│  └─ api_foam_upload_inspect (POST) + recipe_id             │
│                                                              │
│  apps/vision/services.py                                    │
│  └─ VisionService.inspect_foam(..., recipe_id, use_recipe) │
│                                                              │
│  apps/vision/recipe_utils.py                                │
│  ├─ ensure_default_foam_2d_recipes()                        │
│  ├─ get_active_foam_2d_recipe_by_pos(pos)                   │
│  ├─ serialize_recipe(recipe)                                │
│  └─ build_foam_inspection_config(recipe)                    │
└─────────────────────────────────────────────────────────────┘
                           ↕
┌─────────────────────────────────────────────────────────────┐
│                    Database (PostgreSQL)                    │
├─────────────────────────────────────────────────────────────┤
│  vision_visionrecipe                                        │
│  ├─ id, recipe_type, name, pos                              │
│  ├─ roi_config (JSONField)                                  │
│  ├─ threshold_config (JSONField)                            │
│  └─ is_active, updated_at                                   │
│                                                              │
│  vision_foaminspectionresult                                │
│  └─ result_data (JSONField with recipe metadata)           │
└─────────────────────────────────────────────────────────────┘
```

## Data Model Design

### VisionRecipe Model (Existing)

```python
class VisionRecipe(TimeStampedModel):
    recipe_type = models.CharField(max_length=32)  # 'FOAM_2D'
    name = models.CharField(max_length=100)
    pos = models.IntegerField(default=0)  # 0, 1, 2
    camera_side = models.CharField(max_length=20, default='both')
    image_width = models.IntegerField(default=1280)
    image_height = models.IntegerField(default=720)
    
    # ROI Configuration (JSONField)
    roi_config = models.JSONField(default=dict, blank=True)
    # Structure:
    # {
    #   "leftFoamROI": {"x": 220, "y": 140, "width": 90, "height": 70},
    #   "rightFoamROI": {"x": 780, "y": 140, "width": 110, "height": 70}
    # }
    
    # Threshold Configuration (JSONField)
    threshold_config = models.JSONField(default=dict, blank=True)
    # Structure:
    # {
    #   "minCoverage": 0.75,
    #   "minScore": 0.8,
    #   "maxOffsetX": 30,
    #   "maxOffsetY": 30
    # }
    
    is_active = models.BooleanField(default=True)
    remark = models.TextField(blank=True, null=True)
```

### Frontend State Management

```javascript
// Global Recipe State
let foam2DRecipes = [];           // All FOAM_2D recipes from DB
let currentPosIndex = 0;          // Current POS (0/1/2)
let manualSelectedRecipe = null;  // Temporarily selected recipe
let cachedRecipeROIs = {          // Cached pixel ROIs for visualization
  left: null,   // {x, y, width, height}
  right: null   // {x, y, width, height}
};

// Recipe Selection Logic
function activeFoam2DRecipe() {
  // Returns the recipe matching current POS
  return foam2DRecipes.find(r => r.pos === currentPosIndex) || null;
}

function currentDetectionRecipe() {
  // Priority: manual selection > active recipe by POS
  return manualSelectedRecipe || activeFoam2DRecipe();
}
```

## API Interface Design

### Existing APIs (Already Implemented)

#### GET /vision/api/recipes/
```
Query Parameters:
  - recipe_type: "FOAM_2D"
  - pos: 0/1/2 (optional)
  - is_active: true (optional)

Response:
{
  "success": true,
  "recipes": [
    {
      "id": 1,
      "name": "第1层泡棉检测配方",
      "recipe_type": "FOAM_2D",
      "pos": 0,
      "roi_config": {...},
      "threshold_config": {...},
      "is_active": true
    }
  ]
}
```

#### POST /vision/api/recipes/foam-2d/save/
```
Request Body:
{
  "id": 1,  // Optional, omit to create new
  "pos": 0,
  "name": "第1层泡棉检测配方",
  "camera_side": "both",
  "image_width": 1280,
  "image_height": 720,
  "roi_config": {
    "leftFoamROI": {"x": 220, "y": 140, "width": 90, "height": 70},
    "rightFoamROI": {"x": 780, "y": 140, "width": 110, "height": 70}
  },
  "threshold_config": {
    "minCoverage": 0.75,
    "minScore": 0.8,
    "maxOffsetX": 30,
    "maxOffsetY": 30
  },
  "is_active": true
}

Response:
{
  "success": true,
  "recipe": {...}  // Full recipe object
}
```

### Extended APIs (Need Modification)

#### POST /vision/api/foam/capture-inspect/
```
Request Body (New Fields):
{
  "position_index": 0,
  "product_id": 123,
  "rack_id": 456,
  "simulated_pass": false,
  "recipe_id": 1,        // NEW: Optional recipe ID
  "use_recipe": true     // NEW: Whether to use recipe
}

Response (Enhanced):
{
  "success": true,
  "result": {
    "is_passed": true,
    "position_index": 0,
    ...
    "recipe_used": {     // NEW: Recipe metadata
      "id": 1,
      "name": "第1层泡棉检测配方",
      "pos": 0
    }
  }
}
```

#### POST /vision/api/foam/upload-inspect/
```
FormData Fields (New):
  - file: <image file>
  - position_index: 0
  - product_id: 123
  - rack_id: 456
  - recipe_id: 1        // NEW
  - use_recipe: true    // NEW

Response: Same as capture-inspect
```

## Core Algorithm Design

### 1. ROI Coordinate Conversion

```python
# apps/vision/recipe_utils.py

def _pixel_roi_to_ratio(roi, image_width, image_height):
    """Convert pixel ROI to ratio format for FoamInspector."""
    x = float(roi.get('x', 0))
    y = float(roi.get('y', 0))
    width = float(roi.get('width', 0))
    height = float(roi.get('height', 0))
    
    image_width = max(float(image_width or 1), 1.0)
    image_height = max(float(image_height or 1), 1.0)
    
    # Convert to [x1, y1, x2, y2] ratio format
    return [
        round(max(0.0, min(1.0, x / image_width)), 6),
        round(max(0.0, min(1.0, y / image_height)), 6),
        round(max(0.0, min(1.0, (x + width) / image_width)), 6),
        round(max(0.0, min(1.0, (y + height) / image_height)), 6),
    ]
```

### 2. Recipe Configuration Builder

```python
# apps/vision/recipe_utils.py

def build_foam_inspection_config(recipe):
    """Build FoamInspector config from VisionRecipe."""
    roi_config = recipe.roi_config or {}
    thresholds = recipe.threshold_config or {}
    
    left = _pixel_roi_to_ratio(
        roi_config.get('leftFoamROI', {}),
        recipe.image_width,
        recipe.image_height
    )
    right = _pixel_roi_to_ratio(
        roi_config.get('rightFoamROI', {}),
        recipe.image_width,
        recipe.image_height
    )
    
    return {
        'foam_rois': {
            str(recipe.pos): {
                'left': left,
                'right': right,
            }
        },
        'coverage_threshold': float(thresholds.get('minCoverage', 0.75)),
        'score_threshold': float(thresholds.get('minScore', 0.8)),
        'max_offset_px': max(
            int(thresholds.get('maxOffsetX', 30)),
            int(thresholds.get('maxOffsetY', 30))
        ),
    }
```

### 3. Recipe Matching Logic

```python
# apps/vision/recipe_utils.py

def get_active_foam_2d_recipe_by_pos(pos):
    """Get the active recipe for given POS."""
    return (
        VisionRecipe.objects
        .filter(
            recipe_type='FOAM_2D',
            pos=int(pos),
            is_active=True
        )
        .order_by('-updated_at', '-id')
        .first()
    )
```

### 4. Frontend ROI Visualization

```javascript
// foam_inspector_interactive.html

function drawRecipeROIs(recipe) {
  if (!recipe || !recipe.roi_config) {
    clearROIOverlay();
    return;
  }
  
  const leftROI = recipe.roi_config.leftFoamROI;
  const rightROI = recipe.roi_config.rightFoamROI;
  
  const canvas = document.getElementById('roi-canvas');
  const ctx = canvas.getContext('2d');
  
  // Clear previous drawings
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  
  // Draw left foam ROI (green)
  if (leftROI) {
    ctx.strokeStyle = '#10b981';  // Green
    ctx.lineWidth = 2;
    ctx.strokeRect(leftROI.x, leftROI.y, leftROI.width, leftROI.height);
    ctx.fillStyle = 'rgba(16, 185, 129, 0.1)';
    ctx.fillRect(leftROI.x, leftROI.y, leftROI.width, leftROI.height);
    
    // Label
    ctx.fillStyle = '#10b981';
    ctx.font = '12px sans-serif';
    ctx.fillText('左泡棉', leftROI.x + 5, leftROI.y + 15);
  }
  
  // Draw right foam ROI (blue)
  if (rightROI) {
    ctx.strokeStyle = '#3b82f6';  // Blue
    ctx.lineWidth = 2;
    ctx.strokeRect(rightROI.x, rightROI.y, rightROI.width, rightROI.height);
    ctx.fillStyle = 'rgba(59, 130, 246, 0.1)';
    ctx.fillRect(rightROI.x, rightROI.y, rightROI.width, rightROI.height);
    
    // Label
    ctx.fillStyle = '#3b82f6';
    ctx.font = '12px sans-serif';
    ctx.fillText('右泡棉', rightROI.x + 5, rightROI.y + 15);
  }
}
```

## Business Process Design

### Process 1: Page Load with Recipe Auto-Loading

```
1. User opens foam_inspector_interactive.html
2. DOMContentLoaded event triggers
3. Frontend calls loadRecipes()
   ↓
4. GET /vision/api/recipes/?recipe_type=FOAM_2D&is_active=true
   ↓
5. Backend returns all active FOAM_2D recipes
   ↓
6. Frontend caches recipes in foam2DRecipes array
7. Frontend reads currentPosIndex (default 0)
8. Frontend calls activeFoam2DRecipe() to find POS 0 recipe
9. Frontend calls renderRecipeCard() to display recipe info
10. Frontend calls drawRecipeROIs() to visualize ROI on camera feed
```

### Process 2: Calibrate ROI and Save to Specified POS

```
1. User drags to draw ROI boxes on camera feed
2. Frontend captures left/right ROI coordinates (pixel)
3. User clicks "Save Recipe" button
   ↓
4. Frontend shows POS selector dialog (POS 0/1/2)
5. User selects POS (e.g., POS 1)
6. User clicks "Confirm"
   ↓
7. Frontend calls saveRoiToRecipe(selectedPOS)
   ↓
8. POST /vision/api/recipes/foam-2d/save/
   Body: {
     pos: 1,
     roi_config: {leftFoamROI: {...}, rightFoamROI: {...}},
     threshold_config: {...}
   }
   ↓
9. Backend validates ROI data
10. Backend calls VisionRecipe.objects.update_or_create(
      recipe_type='FOAM_2D', pos=1, camera_side='both',
      defaults={...}
    )
11. Backend returns updated recipe
    ↓
12. Frontend shows success message "配方已保存到 POS 1"
13. Frontend reloads recipes (loadRecipes())
14. Frontend updates UI to reflect saved recipe
```

### Process 3: Temporarily Switch Recipe for Detection

```
1. User clicks "Temporarily Use Other Recipe" button
2. Frontend shows recipe selector with all recipes
3. User selects a recipe (e.g., POS 2 recipe)
   ↓
4. Frontend sets manualSelectedRecipe = foam2DRecipes[2]
5. Frontend updates recipe card UI (orange background for temp)
6. Frontend calls drawRecipeROIs(manualSelectedRecipe)
   ↓
7. User clicks "Capture Inspect"
8. Frontend calls currentDetectionRecipe()
   → Returns manualSelectedRecipe (POS 2)
9. Frontend sends POST /vision/api/foam/capture-inspect/
   Body: {
     position_index: 0,  // Current POS is still 0
     recipe_id: 3,       // But use POS 2 recipe
     use_recipe: true
   }
   ↓
10. Backend processes with recipe_id=3
11. Detection completes
12. Frontend keeps manualSelectedRecipe until:
    - User manually clears it, OR
    - User switches POS
```

### Process 4: Detection with Recipe Parameters

```
1. User clicks "Capture Inspect" or uploads image
2. Frontend determines recipe to use:
   recipe = currentDetectionRecipe()
   ↓
3. Frontend sends POST request with recipe_id
   ↓
4. Backend API (api_foam_capture_inspect or api_foam_upload_inspect)
5. Backend calls VisionService.inspect_foam(
     product, rack, position_index,
     recipe_id=recipe_id,
     use_recipe=True
   )
   ↓
6. VisionService logic:
   a. If recipe_id provided:
      → Load VisionRecipe by ID
   b. Else if use_recipe=True:
      → Call get_active_foam_2d_recipe_by_pos(position_index)
   c. If recipe found:
      → Call build_foam_inspection_config(recipe)
      → Convert pixel ROI to ratio ROI
   d. Merge configs (priority: recipe > calibration > manual)
   e. Call FoamInspector.inspect() with merged config
   f. Save recipe metadata to FoamInspectionResult.result_data
   ↓
7. Backend returns result with recipe info
   ↓
8. Frontend displays result with recipe name and POS
9. Result image shows ROI boxes
```

## Technical Stack

### Backend
- **Framework**: Django 4.x
- **Language**: Python 3.10+
- **Database**: PostgreSQL (JSONField for roi_config)
- **ORM**: Django ORM

### Frontend
- **Template Engine**: Django Template Language
- **JavaScript**: Native ES6+ (no frameworks)
- **Visualization**: HTML5 Canvas API
- **HTTP Client**: Fetch API
- **Styling**: CSS3 (existing project styles)

### Integration
- **Existing Components**: VisionRecipe model, recipe_utils.py already implemented
- **Modifications Needed**: foam_inspector_interactive.html, api views
- **No Breaking Changes**: Backward compatible with CalibrationProfile

## Backward Compatibility Strategy

### Priority Chain
```
Manual ROI (highest)
  ↓ (if not provided)
VisionRecipe
  ↓ (if not found)
CalibrationProfile
  ↓ (if not found)
Default Values (lowest)
```

### Implementation
```python
# In VisionService.inspect_foam()

merged_config = {}

# Layer 1: Manual inspection_config (highest priority)
if inspection_config:
    merged_config.update(inspection_config)

# Layer 2: CalibrationProfile
profile, calibration_config = self._foam_calibration_config(camera_code)
merged_config.update(calibration_config)

# Layer 3: VisionRecipe (highest priority if exists)
if use_recipe:
    recipe = load_recipe(recipe_id, position_index)
    if recipe:
        recipe_config = build_foam_inspection_config(recipe)
        merged_config.update(recipe_config)

# Fallback: FoamInspector has default ROIs built-in
```

### Error Handling
- **No Recipe Found**: Use CalibrationProfile or defaults, DO NOT fail
- **Invalid ROI Data**: Log warning, use defaults
- **API Errors**: Return graceful error messages, allow manual operation
