# Tasks

## Phase 1: Backend API Enhancement

### Task 1.1: Extend api_foam_capture_inspect to accept recipe_id
**Status**: pending  
**Description**: 修改拍照检测 API，接收并处理 recipe_id 和 use_recipe 参数

**Files**:
- `apps/vision/views.py` (api_foam_capture_inspect function)

**Implementation**:
```python
@csrf_exempt
@require_http_methods(['POST'])
def api_foam_capture_inspect(request):
    body = json.loads(request.body)
    position_index = int(body.get('position_index', 0))
    recipe_id = body.get('recipe_id')  # NEW
    use_recipe = body.get('use_recipe', True)  # NEW
    
    result = VisionService().inspect_foam(
        product=product,
        rack=rack,
        position_index=position_index,
        recipe_id=recipe_id,  # Pass to service
        use_recipe=use_recipe,
        use_camera=True,
    )
    
    return JsonResponse({
        'success': True,
        'result': {
            ...
            'recipe_used': result.result_data.get('recipe'),  # NEW
        }
    })
```

**Acceptance Criteria**:
- [ ] API accepts recipe_id (int, optional)
- [ ] API accepts use_recipe (bool, default True)
- [ ] recipe_id passed to VisionService.inspect_foam()
- [ ] Response includes recipe_used metadata
- [ ] Existing tests still pass

**Estimated Effort**: 1 hour

---

### Task 1.2: Extend api_foam_upload_inspect to accept recipe_id
**Status**: pending  
**Description**: 修改上传图片检测 API，接收并处理 recipe_id 参数

**Files**:
- `apps/vision/views.py` (api_foam_upload_inspect function)

**Implementation**:
```python
@csrf_exempt
@require_http_methods(['POST'])
def api_foam_upload_inspect(request):
    recipe_id = request.POST.get('recipe_id')  # NEW
    use_recipe = request.POST.get('use_recipe', 'true').lower() == 'true'  # NEW
    
    result = VisionService().inspect_foam(
        product=product,
        rack=rack,
        position_index=position_index,
        recipe_id=int(recipe_id) if recipe_id else None,
        use_recipe=use_recipe,
        use_camera=False,
        upload_image=uploaded_file,
    )
    
    return JsonResponse({...})
```

**Acceptance Criteria**:
- [ ] API accepts recipe_id from FormData
- [ ] API accepts use_recipe from FormData
- [ ] Parameters passed to VisionService
- [ ] Response includes recipe metadata

**Estimated Effort**: 1 hour

**Dependencies**: None

---

### Task 1.3: Verify VisionService.inspect_foam recipe support
**Status**: pending  
**Description**: 确认 VisionService.inspect_foam() 已正确实现 recipe_id 和 use_recipe 参数支持

**Files**:
- `apps/vision/services.py` (VisionService.inspect_foam method)

**Verification Points**:
- [x] Method signature includes recipe_id and use_recipe parameters (ALREADY DONE)
- [x] Recipe loading logic implemented (ALREADY DONE)
- [x] build_foam_inspection_config() called for recipe (ALREADY DONE)
- [x] Recipe metadata saved to result_data (ALREADY DONE)
- [ ] Add unit tests for recipe integration

**Acceptance Criteria**:
- [ ] Unit test: inspect_foam with recipe_id uses specified recipe
- [ ] Unit test: inspect_foam without recipe_id uses POS-matched recipe
- [ ] Unit test: inspect_foam with use_recipe=False ignores recipes
- [ ] Unit test: No recipe found → fallback to CalibrationProfile
- [ ] Integration test: Recipe ROI correctly converted to inspector format

**Estimated Effort**: 2 hours

**Dependencies**: None

---

## Phase 2: Frontend State Management

### Task 2.1: Add recipe state variables to workbench
**Status**: pending  
**Description**: 在 foam_inspector_interactive.html 中添加配方状态管理变量

**Files**:
- `templates/vision/foam_inspector_interactive.html`

**Implementation**:
```javascript
// Add to <script> section
let foam2DRecipes = [];           // All FOAM_2D recipes
let currentPosIndex = 0;          // Current POS (0/1/2)
let manualSelectedRecipe = null;  // Temporary recipe selection
let cachedRecipeROIs = {          // For visualization
  left: null,
  right: null
};

function activeFoam2DRecipe() {
  return foam2DRecipes.find(r => r.pos === currentPosIndex) || null;
}

function currentDetectionRecipe() {
  return manualSelectedRecipe || activeFoam2DRecipe();
}

function clearManualRecipe() {
  manualSelectedRecipe = null;
  renderRecipeCard();
}
```

**Acceptance Criteria**:
- [ ] State variables declared at global scope
- [ ] activeFoam2DRecipe() returns correct recipe for current POS
- [ ] currentDetectionRecipe() prioritizes manual selection
- [ ] clearManualRecipe() resets temporary state

**Estimated Effort**: 1 hour

**Dependencies**: None

---

### Task 2.2: Implement loadRecipes() function
**Status**: pending  
**Description**: 实现从后端加载配方列表的函数

**Files**:
- `templates/vision/foam_inspector_interactive.html`

**Implementation**:
```javascript
async function loadRecipes() {
  try {
    const response = await fetch('/vision/api/recipes/?recipe_type=FOAM_2D&is_active=true');
    const data = await response.json();
    
    if (data.success) {
      foam2DRecipes = data.recipes || [];
      console.log(`Loaded ${foam2DRecipes.length} FOAM_2D recipes`);
      renderRecipeCard();
      drawRecipeROIs(currentDetectionRecipe());
    } else {
      console.error('Failed to load recipes:', data.error);
    }
  } catch (error) {
    console.error('Error loading recipes:', error);
  }
}

// Call on page load
document.addEventListener('DOMContentLoaded', () => {
  loadRecipes();
  // ... existing init code
});
```

**Acceptance Criteria**:
- [ ] Function calls GET /vision/api/recipes/
- [ ] Recipes cached in foam2DRecipes array
- [ ] renderRecipeCard() called after loading
- [ ] drawRecipeROIs() called with current recipe
- [ ] Error handling for network failures

**Estimated Effort**: 1.5 hours

**Dependencies**: Task 2.1

---

### Task 2.3: Sync currentPosIndex with #pos-index input
**Status**: pending  
**Description**: 将 currentPosIndex 与页面上的 #pos-index 输入框同步

**Files**:
- `templates/vision/foam_inspector_interactive.html`

**Implementation**:
```javascript
// Add event listener to POS input
const posInput = document.getElementById('pos-index');
if (posInput) {
  posInput.addEventListener('change', () => {
    currentPosIndex = parseInt(posInput.value) || 0;
    clearManualRecipe();  // Clear temp selection on POS change
    renderRecipeCard();
    drawRecipeROIs(currentDetectionRecipe());
  });
  
  // Initialize from input value
  currentPosIndex = parseInt(posInput.value) || 0;
}
```

**Acceptance Criteria**:
- [ ] POS input change updates currentPosIndex
- [ ] Manual recipe selection cleared on POS change
- [ ] Recipe card UI updates to show new POS recipe
- [ ] ROI visualization updates to new recipe

**Estimated Effort**: 0.5 hours

**Dependencies**: Task 2.1, Task 2.2

---

## Phase 3: Recipe Information Display

### Task 3.1: Add recipe info card HTML structure
**Status**: pending  
**Description**: 在工作台页面添加配方信息卡片的 HTML 结构

**Files**:
- `templates/vision/foam_inspector_interactive.html`

**Implementation**:
```html
<!-- Add near top of page, after title -->
<div id="recipe-info-card" class="recipe-info-card" style="display:none;">
  <div class="recipe-info-header">
    <span class="recipe-info-title">当前配方</span>
    <button id="btn-temp-recipe" class="btn btn-sm btn-secondary">临时使用其他配方</button>
    <button id="btn-clear-temp" class="btn btn-sm btn-secondary" style="display:none;">清除临时配方</button>
  </div>
  <div class="recipe-info-body">
    <div class="recipe-info-row">
      <strong>POS:</strong> <span id="recipe-pos">-</span>
    </div>
    <div class="recipe-info-row">
      <strong>配方名称:</strong> <span id="recipe-name">-</span>
    </div>
    <div class="recipe-info-row">
      <strong>左ROI:</strong> <span id="recipe-left-roi">-</span>
    </div>
    <div class="recipe-info-row">
      <strong>右ROI:</strong> <span id="recipe-right-roi">-</span>
    </div>
    <div class="recipe-info-row">
      <strong>阈值:</strong> <span id="recipe-thresholds">-</span>
    </div>
  </div>
</div>

<style>
.recipe-info-card {
  background: #e0f2fe;
  border: 1px solid #0284c7;
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 16px;
}
.recipe-info-card.temp {
  background: #fed7aa;
  border-color: #f59e0b;
}
.recipe-info-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.recipe-info-title {
  font-weight: 700;
  font-size: 14px;
}
.recipe-info-row {
  font-size: 13px;
  margin: 4px 0;
  color: #1f2937;
}
</style>
```

**Acceptance Criteria**:
- [ ] Card hidden by default (display:none)
- [ ] Normal recipe uses blue background
- [ ] Temporary recipe uses orange background (.temp class)
- [ ] Shows POS, name, ROI coordinates, thresholds
- [ ] Buttons for temp selection and clearing

**Estimated Effort**: 1 hour

**Dependencies**: None

---

### Task 3.2: Implement renderRecipeCard() function
**Status**: pending  
**Description**: 实现配方信息卡片渲染函数

**Files**:
- `templates/vision/foam_inspector_interactive.html`

**Implementation**:
```javascript
function renderRecipeCard() {
  const card = document.getElementById('recipe-info-card');
  const recipe = currentDetectionRecipe();
  
  if (!recipe) {
    card.style.display = 'none';
    return;
  }
  
  card.style.display = 'block';
  
  // Toggle temp class
  if (manualSelectedRecipe) {
    card.classList.add('temp');
    document.getElementById('btn-clear-temp').style.display = '';
  } else {
    card.classList.remove('temp');
    document.getElementById('btn-clear-temp').style.display = 'none';
  }
  
  // Populate data
  document.getElementById('recipe-pos').textContent = recipe.pos;
  document.getElementById('recipe-name').textContent = recipe.name;
  
  const left = recipe.roi_config?.leftFoamROI || {};
  const right = recipe.roi_config?.rightFoamROI || {};
  document.getElementById('recipe-left-roi').textContent = 
    `x=${left.x || 0}, y=${left.y || 0}, w=${left.width || 0}, h=${left.height || 0}`;
  document.getElementById('recipe-right-roi').textContent = 
    `x=${right.x || 0}, y=${right.y || 0}, w=${right.width || 0}, h=${right.height || 0}`;
  
  const thresh = recipe.threshold_config || {};
  document.getElementById('recipe-thresholds').textContent = 
    `覆盖率≥${thresh.minCoverage || 0.75}, 得分≥${thresh.minScore || 0.8}`;
}
```

**Acceptance Criteria**:
- [ ] Card hidden when no recipe available
- [ ] Card shown when recipe exists
- [ ] Temporary recipe adds .temp class (orange background)
- [ ] All recipe fields populated correctly
- [ ] Clear button shown only for temp recipes

**Estimated Effort**: 1.5 hours

**Dependencies**: Task 2.1, Task 2.2, Task 3.1

---

## Phase 4: ROI Visualization

### Task 4.1: Create ROI canvas overlay
**Status**: pending  
**Description**: 在相机画面上创建 Canvas 覆盖层用于绘制 ROI

**Files**:
- `templates/vision/foam_inspector_interactive.html`

**Implementation**:
```html
<!-- Add canvas overlay to camera feed container -->
<div id="camera-feed-container" style="position:relative;">
  <img id="camera-feed" src="..." />
  <canvas id="roi-canvas" style="position:absolute;top:0;left:0;pointer-events:none;"></canvas>
</div>

<script>
// Sync canvas size with image
function syncCanvasSize() {
  const img = document.getElementById('camera-feed');
  const canvas = document.getElementById('roi-canvas');
  canvas.width = img.clientWidth;
  canvas.height = img.clientHeight;
}

window.addEventListener('resize', syncCanvasSize);
document.getElementById('camera-feed').addEventListener('load', syncCanvasSize);
</script>
```

**Acceptance Criteria**:
- [ ] Canvas overlays camera feed exactly
- [ ] Canvas resizes with image/window
- [ ] Canvas doesn't block mouse events (pointer-events:none)
- [ ] Canvas cleared on recipe change

**Estimated Effort**: 1 hour

**Dependencies**: None

---

### Task 4.2: Implement drawRecipeROIs() function
**Status**: pending  
**Description**: 实现在 Canvas 上绘制配方 ROI 框的函数

**Files**:
- `templates/vision/foam_inspector_interactive.html`

**Implementation**:
```javascript
function drawRecipeROIs(recipe) {
  const canvas = document.getElementById('roi-canvas');
  const ctx = canvas.getContext('2d');
  
  // Clear previous drawings
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  
  if (!recipe || !recipe.roi_config) {
    return;
  }
  
  const leftROI = recipe.roi_config.leftFoamROI;
  const rightROI = recipe.roi_config.rightFoamROI;
  
  // Calculate scale factors
  const img = document.getElementById('camera-feed');
  const scaleX = canvas.width / (recipe.image_width || 1280);
  const scaleY = canvas.height / (recipe.image_height || 720);
  
  // Draw left foam ROI (green)
  if (leftROI) {
    const x = leftROI.x * scaleX;
    const y = leftROI.y * scaleY;
    const w = leftROI.width * scaleX;
    const h = leftROI.height * scaleY;
    
    ctx.strokeStyle = '#10b981';
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = 'rgba(16, 185, 129, 0.1)';
    ctx.fillRect(x, y, w, h);
    
    // Label
    ctx.fillStyle = '#10b981';
    ctx.font = 'bold 14px sans-serif';
    ctx.fillText('左泡棉', x + 5, y + 18);
  }
  
  // Draw right foam ROI (blue)
  if (rightROI) {
    const x = rightROI.x * scaleX;
    const y = rightROI.y * scaleY;
    const w = rightROI.width * scaleX;
    const h = rightROI.height * scaleY;
    
    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = 'rgba(59, 130, 246, 0.1)';
    ctx.fillRect(x, y, w, h);
    
    // Label
    ctx.fillStyle = '#3b82f6';
    ctx.font = 'bold 14px sans-serif';
    ctx.fillText('右泡棉', x + 5, y + 18);
  }
}
```

**Acceptance Criteria**:
- [ ] Left ROI drawn in green with label
- [ ] Right ROI drawn in blue with label
- [ ] ROIs scaled correctly to canvas size
- [ ] Translucent fill doesn't obscure camera feed
- [ ] Canvas cleared when no recipe

**Estimated Effort**: 2 hours

**Dependencies**: Task 4.1

---

## Phase 5: Save Calibration to Recipe

### Task 5.1: Add "Save Recipe" button and POS dialog
**Status**: pending  
**Description**: 添加保存配方按钮和 POS 选择对话框

**Files**:
- `templates/vision/foam_inspector_interactive.html`

**Implementation**:
```html
<!-- Add button near calibration controls -->
<button id="btn-save-recipe" class="btn btn-primary">保存配方到指定POS</button>

<!-- Add modal dialog at end of page -->
<div id="pos-selector-modal" class="modal" style="display:none;">
  <div class="modal-content">
    <h3>选择保存到哪个 POS</h3>
    <div class="pos-options">
      <button class="btn btn-pos" data-pos="0">POS 0 (第1层)</button>
      <button class="btn btn-pos" data-pos="1">POS 1 (第2层)</button>
      <button class="btn btn-pos" data-pos="2">POS 2 (第3层)</button>
    </div>
    <button class="btn btn-secondary" id="btn-cancel-pos">取消</button>
  </div>
</div>

<style>
.modal {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}
.modal-content {
  background: white;
  padding: 24px;
  border-radius: 8px;
  min-width: 300px;
}
.pos-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 16px 0;
}
</style>
```

**Acceptance Criteria**:
- [ ] Button visible in calibration section
- [ ] Modal hidden by default
- [ ] Modal shows 3 POS options
- [ ] Cancel button closes modal
- [ ] Modal prevents interaction with page beneath

**Estimated Effort**: 1 hour

**Dependencies**: None

---

### Task 5.2: Implement saveRoiToRecipe() function
**Status**: pending  
**Description**: 实现保存当前标定的 ROI 到指定 POS 配方的函数

**Files**:
- `templates/vision/foam_inspector_interactive.html`

**Implementation**:
```javascript
let calibratedROIs = {  // Captured from drag calibration
  left: null,
  right: null
};

async function saveRoiToRecipe(targetPos) {
  if (!calibratedROIs.left || !calibratedROIs.right) {
    alert('请先标定左右泡棉 ROI');
    return;
  }
  
  // Find existing recipe or create new
  const existingRecipe = foam2DRecipes.find(r => r.pos === targetPos);
  
  const payload = {
    id: existingRecipe?.id,
    pos: targetPos,
    name: `第${targetPos + 1}层泡棉检测配方`,
    camera_side: 'both',
    image_width: 1280,
    image_height: 720,
    roi_config: {
      leftFoamROI: calibratedROIs.left,
      rightFoamROI: calibratedROIs.right
    },
    threshold_config: existingRecipe?.threshold_config || {
      minCoverage: 0.75,
      minScore: 0.8,
      maxOffsetX: 30,
      maxOffsetY: 30
    },
    is_active: true
  };
  
  try {
    const response = await fetch('/vision/api/recipes/foam-2d/save/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify(payload)
    });
    
    const data = await response.json();
    
    if (data.success) {
      alert(`配方已保存到 POS ${targetPos}`);
      await loadRecipes();  // Reload recipes
      document.getElementById('pos-selector-modal').style.display = 'none';
    } else {
      alert('保存失败: ' + (data.error || '未知错误'));
    }
  } catch (error) {
    alert('网络错误: ' + error.message);
  }
}

// Hook up button events
document.getElementById('btn-save-recipe').addEventListener('click', () => {
  document.getElementById('pos-selector-modal').style.display = 'flex';
});

document.querySelectorAll('.btn-pos').forEach(btn => {
  btn.addEventListener('click', () => {
    const pos = parseInt(btn.dataset.pos);
    saveRoiToRecipe(pos);
  });
});

document.getElementById('btn-cancel-pos').addEventListener('click', () => {
  document.getElementById('pos-selector-modal').style.display = 'none';
});
```

**Acceptance Criteria**:
- [ ] Function validates ROIs are calibrated
- [ ] Function finds existing recipe or creates new
- [ ] POST request sent to save API
- [ ] Success message shows target POS
- [ ] Recipes reloaded after save
- [ ] Modal closes after save
- [ ] Saves only to selected POS, doesn't affect others

**Estimated Effort**: 2 hours

**Dependencies**: Task 5.1

---

## Phase 6: Temporary Recipe Selection

### Task 6.1: Implement temporary recipe selector
**Status**: pending  
**Description**: 实现临时切换配方的选择器

**Files**:
- `templates/vision/foam_inspector_interactive.html`

**Implementation**:
```javascript
function showTempRecipeSelector() {
  const modal = document.getElementById('temp-recipe-modal');
  const list = document.getElementById('temp-recipe-list');
  
  list.innerHTML = foam2DRecipes.map(recipe => `
    <button class="btn-select-temp-recipe" data-recipe-id="${recipe.id}">
      <strong>POS ${recipe.pos}</strong> - ${recipe.name}
      <div style="font-size:12px;color:#666;">
        左ROI: x=${recipe.roi_config.leftFoamROI?.x}, y=${recipe.roi_config.leftFoamROI?.y}
      </div>
    </button>
  `).join('');
  
  modal.style.display = 'flex';
}

document.getElementById('btn-temp-recipe').addEventListener('click', showTempRecipeSelector);

document.addEventListener('click', (e) => {
  if (e.target.classList.contains('btn-select-temp-recipe')) {
    const recipeId = parseInt(e.target.dataset.recipeId);
    manualSelectedRecipe = foam2DRecipes.find(r => r.id === recipeId);
    renderRecipeCard();
    drawRecipeROIs(manualSelectedRecipe);
    document.getElementById('temp-recipe-modal').style.display = 'none';
  }
});

document.getElementById('btn-clear-temp').addEventListener('click', clearManualRecipe);
```

**Acceptance Criteria**:
- [ ] Selector shows all available recipes
- [ ] Each recipe shows POS, name, and ROI preview
- [ ] Selecting recipe sets manualSelectedRecipe
- [ ] Recipe card updates to temp mode (orange)
- [ ] ROI visualization updates
- [ ] Clear button resets to POS-matched recipe

**Estimated Effort**: 2 hours

**Dependencies**: Task 2.1, Task 2.2, Task 3.2

---

## Phase 7: Detection Integration

### Task 7.1: Modify capture inspect to send recipe_id
**Status**: pending  
**Description**: 修改拍照检测逻辑，携带当前配方 ID

**Files**:
- `templates/vision/foam_inspector_interactive.html`

**Implementation**:
```javascript
// Find existing captureInspect() or similar function
async function captureInspect() {
  const recipe = currentDetectionRecipe();
  const pos = currentPosIndex;
  
  const payload = {
    position_index: pos,
    product_id: currentProductId,
    rack_id: currentRackId,
    simulated_pass: false,
    recipe_id: recipe?.id || null,  // NEW
    use_recipe: true                // NEW
  };
  
  try {
    const response = await fetch('/vision/api/foam/capture-inspect/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify(payload)
    });
    
    const data = await response.json();
    
    if (data.success) {
      displayInspectionResult(data.result);
      // Clear manual selection after detection
      if (manualSelectedRecipe) {
        clearManualRecipe();
      }
    }
  } catch (error) {
    console.error('Detection failed:', error);
  }
}
```

**Acceptance Criteria**:
- [ ] recipe_id included in request body
- [ ] use_recipe set to true
- [ ] Manual selection cleared after detection
- [ ] Result displayed with recipe info
- [ ] Error handling for failed detection

**Estimated Effort**: 1.5 hours

**Dependencies**: Task 1.1, Task 2.1

---

### Task 7.2: Modify upload inspect to send recipe_id
**Status**: pending  
**Description**: 修改上传图片检测逻辑，携带当前配方 ID

**Files**:
- `templates/vision/foam_inspector_interactive.html`

**Implementation**:
```javascript
async function uploadInspect(file) {
  const recipe = currentDetectionRecipe();
  const pos = currentPosIndex;
  
  const formData = new FormData();
  formData.append('file', file);
  formData.append('position_index', pos);
  formData.append('product_id', currentProductId);
  formData.append('rack_id', currentRackId);
  formData.append('recipe_id', recipe?.id || '');  // NEW
  formData.append('use_recipe', 'true');            // NEW
  
  try {
    const response = await fetch('/vision/api/foam/upload-inspect/', {
      method: 'POST',
      headers: {
        'X-CSRFToken': getCsrfToken()
      },
      body: formData
    });
    
    const data = await response.json();
    
    if (data.success) {
      displayInspectionResult(data.result);
      if (manualSelectedRecipe) {
        clearManualRecipe();
      }
    }
  } catch (error) {
    console.error('Upload inspection failed:', error);
  }
}
```

**Acceptance Criteria**:
- [ ] recipe_id appended to FormData
- [ ] use_recipe appended to FormData
- [ ] Manual selection cleared after detection
- [ ] Result displayed with recipe info

**Estimated Effort**: 1 hour

**Dependencies**: Task 1.2, Task 2.1

---

### Task 7.3: Enhance result display with recipe info
**Status**: pending  
**Description**: 在检测结果区域显示使用的配方信息

**Files**:
- `templates/vision/foam_inspector_interactive.html`

**Implementation**:
```javascript
function displayInspectionResult(result) {
  // ... existing result display code ...
  
  // Add recipe info section
  const recipeUsed = result.recipe_used || result.result_data?.recipe;
  
  if (recipeUsed) {
    const recipeInfoHtml = `
      <div class="result-recipe-info">
        <h4>使用配方</h4>
        <p><strong>POS ${recipeUsed.pos}:</strong> ${recipeUsed.name}</p>
        <p><strong>左ROI:</strong> x=${recipeUsed.roi_config.leftFoamROI.x}, 
           y=${recipeUsed.roi_config.leftFoamROI.y}</p>
        <p><strong>右ROI:</strong> x=${recipeUsed.roi_config.rightFoamROI.x}, 
           y=${recipeUsed.roi_config.rightFoamROI.y}</p>
      </div>
    `;
    document.getElementById('result-details').insertAdjacentHTML('beforeend', recipeInfoHtml);
  }
  
  // Show result image (already has ROI annotations from backend)
  document.getElementById('result-image').src = result.result_image_url;
}
```

**Acceptance Criteria**:
- [ ] Recipe info displayed in result section
- [ ] Shows recipe name, POS, ROI coordinates
- [ ] Result image shows ROI annotations (from backend)
- [ ] Gracefully handles missing recipe_used

**Estimated Effort**: 1 hour

**Dependencies**: Task 7.1, Task 7.2

---

## Phase 8: Testing & Validation

### Task 8.1: Unit tests for recipe loading
**Status**: pending  
**Description**: 为配方加载逻辑编写单元测试

**Files**:
- `apps/vision/tests.py`

**Tests to Add**:
```python
def test_get_active_foam_2d_recipe_by_pos_returns_correct_recipe():
    # Create recipes for POS 0, 1, 2
    # Query each POS
    # Assert correct recipe returned

def test_get_active_foam_2d_recipe_returns_most_recent():
    # Create two recipes for same POS
    # Update one
    # Assert most recent returned

def test_build_foam_inspection_config_converts_pixel_to_ratio():
    # Create recipe with pixel ROIs
    # Call build_foam_inspection_config()
    # Assert ratio ROIs correct

def test_build_foam_inspection_config_handles_missing_fields():
    # Create recipe with incomplete roi_config
    # Call build_foam_inspection_config()
    # Assert defaults used
```

**Acceptance Criteria**:
- [ ] All tests pass
- [ ] Edge cases covered (missing ROI, invalid POS)
- [ ] Test coverage >80% for recipe_utils.py

**Estimated Effort**: 2 hours

**Dependencies**: Task 1.3

---

### Task 8.2: Integration tests for save recipe flow
**Status**: pending  
**Description**: 测试标定 ROI 并保存到指定 POS 的完整流程

**Files**:
- `apps/vision/tests.py`

**Tests to Add**:
```python
def test_save_recipe_creates_new_for_empty_pos():
    # POST to save API with POS that has no recipe
    # Assert new VisionRecipe created
    # Assert only that POS affected

def test_save_recipe_updates_existing():
    # Create recipe for POS 0
    # POST to save API with same POS but different ROIs
    # Assert recipe updated, not duplicated

def test_save_recipe_validates_roi_bounds():
    # POST with ROI exceeding image dimensions
    # Assert validation error returned

def test_save_recipe_preserves_other_pos():
    # Create recipes for POS 0, 1, 2
    # Update POS 1
    # Assert POS 0 and 2 unchanged
```

**Acceptance Criteria**:
- [ ] All tests pass
- [ ] API validation tested
- [ ] Multi-POS isolation verified

**Estimated Effort**: 2.5 hours

**Dependencies**: Task 5.2

---

### Task 8.3: Integration tests for detection with recipe
**Status**: pending  
**Description**: 测试使用配方参数进行检测的流程

**Files**:
- `apps/vision/tests.py`

**Tests to Add**:
```python
def test_capture_inspect_uses_explicit_recipe_id():
    # Create recipe
    # POST to capture-inspect with recipe_id
    # Assert result.result_data contains recipe

def test_capture_inspect_auto_matches_recipe_by_pos():
    # Create recipe for POS 1
    # POST to capture-inspect with position_index=1, no recipe_id
    # Assert recipe auto-matched and used

def test_inspect_fallback_to_calibration_when_no_recipe():
    # Delete all recipes
    # POST to capture-inspect
    # Assert detection still works (CalibrationProfile used)

def test_manual_recipe_selection_overrides_pos():
    # Current POS 0, but recipe_id for POS 2
    # Assert POS 2 recipe used
    # Assert result shows correct recipe
```

**Acceptance Criteria**:
- [ ] All tests pass
- [ ] Recipe priority chain verified
- [ ] Fallback behavior confirmed

**Estimated Effort**: 3 hours

**Dependencies**: Task 7.1, Task 7.2

---

### Task 8.4: End-to-end test: Recipe management ↔ Workbench sync
**Status**: pending  
**Description**: 测试配方管理页面和检测工作台之间的数据同步

**Files**:
- `apps/vision/tests.py` or manual test script

**Test Scenario**:
```
1. Open recipe management page
2. Edit POS 1 recipe ROI
3. Save recipe
4. Open workbench page
5. Select POS 1
6. Verify updated ROI displayed
7. Capture inspection
8. Verify result uses updated ROI
```

**Manual Test Checklist**:
- [ ] Recipe update reflects in workbench
- [ ] No cache staleness
- [ ] ROI visualization updates
- [ ] Detection uses new recipe

**Estimated Effort**: 1.5 hours

**Dependencies**: All previous tasks

---

### Task 8.5: Regression test: Backward compatibility
**Status**: pending  
**Description**: 验证系统在无配方情况下的向后兼容性

**Files**:
- `apps/vision/tests.py`

**Tests to Add**:
```python
def test_workbench_works_without_any_recipes():
    # Delete all VisionRecipe records
    # Load workbench page
    # Assert no errors
    # Manual calibration still works

def test_detection_without_recipe_uses_calibration_profile():
    # Delete recipes but keep CalibrationProfile
    # POST to capture-inspect
    # Assert CalibrationProfile used

def test_detection_without_recipe_or_calibration_uses_defaults():
    # Delete all recipes and CalibrationProfile
    # POST to capture-inspect
    # Assert default ROIs used
    # Assert detection doesn't crash
```

**Acceptance Criteria**:
- [ ] All tests pass
- [ ] No breaking changes to existing flows
- [ ] Graceful degradation verified

**Estimated Effort**: 2 hours

**Dependencies**: Task 8.3

---

## Summary

### Total Tasks: 23
### Total Estimated Effort: ~35 hours

### Phase Breakdown:
- **Phase 1 (Backend API)**: 3 tasks, 4 hours
- **Phase 2 (State Management)**: 3 tasks, 3 hours
- **Phase 3 (Recipe Display)**: 2 tasks, 2.5 hours
- **Phase 4 (ROI Visualization)**: 2 tasks, 3 hours
- **Phase 5 (Save Calibration)**: 2 tasks, 3 hours
- **Phase 6 (Temp Selection)**: 1 task, 2 hours
- **Phase 7 (Detection)**: 3 tasks, 3.5 hours
- **Phase 8 (Testing)**: 5 tasks, 11 hours

### Critical Path:
Task 2.1 → Task 2.2 → Task 3.2 → Task 4.2 → Task 7.1 → Task 8.3

### Risk Areas:
1. **ROI coordinate scaling** - Pixel to ratio conversion must be precise
2. **Canvas overlay positioning** - May need adjustments for responsive layout
3. **State synchronization** - POS change must clear temporary selections
4. **Backend config merging** - Priority chain must be tested thoroughly
