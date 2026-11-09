
// ============================================================
//  视觉配方管理 · 前端逻辑 v1.2 (无Loading版本)
// ============================================================
console.log('配方管理页面已加载 - v2.0 (料架/产品/位置三级结构)');

const API = {
  recipes: '/vision/api/recipes/',
  recipeByPos: '/vision/api/recipes/foam-2d/by-pos/',
  saveRecipe: '/vision/api/recipes/foam-2d/save/',
  createRecipe: '/vision/api/recipes/foam-2d/create/',
  deleteRecipe: (id) => `/vision/api/recipes/foam-2d/${id}/delete/`,
  foamRackSpecs: '/vision/api/foam/rack-specs/',
  foamRackSpec: (id) => `/vision/api/foam/rack-specs/${id}/`,
  foamProducts: (rackId) => `/vision/api/foam/rack-specs/${rackId}/products/`,
  foamProduct: (id) => `/vision/api/foam/product-layouts/${id}/`,
  foamLayoutRecipes: (id) => `/vision/api/foam/product-layouts/${id}/recipes/`,
  defaultRecipes: '/vision/api/recipes/foam-2d/defaults/',
  emptyRackRecipe: '/vision/api/recipes/empty-rack-2d/',
  saveEmptyRackRecipe: '/vision/api/recipes/empty-rack-2d/save/',
  rackMasterRecipes: '/vision/api/rack-master-recipes/',
  rackMasterMappingSave: '/vision/api/rack-master-mappings/save/',
  rackMasterValidate: (id) => `/vision/api/rack-master-recipes/${id}/validate/`,
  rackMasterResolve: (id) => `/vision/api/rack-master-recipes/${id}/resolve/`,
  // 3D料架定位配方API
  rack3dRecipes: '/vision/api/rack-location/recipes/',
  rack3dRecipeUpdate: (id) => `/vision/api/rack-location/recipes/${id}/update/`,
};

function getCsrf() {
  return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
}

function showToast(message, type = 'success', duration = 2000) {
  const icons = {
    success: '✅',
    error: '❌',
    info: 'ℹ️'
  };
  
  const titles = {
    success: '操作成功',
    error: '操作失败',
    info: '提示'
  };
  
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <div class="toast-icon">${icons[type]}</div>
    <div class="toast-content">
      <div class="toast-title">${titles[type]}</div>
      <div class="toast-message">${message}</div>
    </div>
  `;
  
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.style.animation = 'slideOutRight 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// 兼容旧代码，但不显示loading
function showLoading(msg = '处理中...') {
  // 不显示loading，静默处理
}

function hideLoading() {
  // 不做任何事
}

// ── 配方状态 ───────────────────────────────────────
let foam2DRecipes = [];
let manualSelectedRecipe = null;
let selectedRecipeForEdit = null;
let currentPosIndex = 0;
let modalMode = 'create'; // 'create' or 'edit'
let editingRecipeId = null;
let foamRackSpecs = [];
let foamProductLayouts = [];
let foamLayoutLayers = [];
let foamCopySources = [];
let foamOverflowRecipes = [];
let selectedFoamRackId = null;
let selectedFoamLayoutId = null;
const initialFoamLayoutId = Number(new URLSearchParams(window.location.search).get('layout_id') || 0);

const FOAM_SYSTEM_PROFILE = {
  rackLayers: 0,
  productCode: '',
  productName: '',
  unitsPerLayer: 0,
};

function selectedFoamRack() {
  return foamRackSpecs.find(item => Number(item.id) === Number(selectedFoamRackId)) || null;
}

function selectedFoamLayout() {
  return foamProductLayouts.find(item => Number(item.id) === Number(selectedFoamLayoutId)) || null;
}

function totalFoamPositions() {
  return FOAM_SYSTEM_PROFILE.rackLayers * FOAM_SYSTEM_PROFILE.unitsPerLayer;
}

function positionMeta(pos) {
  const normalizedPos = Math.max(0, Number(pos) || 0);
  const perLayer = Math.max(FOAM_SYSTEM_PROFILE.unitsPerLayer, 1);
  return {
    pos: normalizedPos,
    globalNumber: normalizedPos + 1,
    layer: Math.floor(normalizedPos / perLayer) + 1,
    slot: normalizedPos % perLayer + 1,
  };
}

function positionLabel(pos) {
  const meta = positionMeta(pos);
  return `第 ${meta.layer} 层 · ${meta.slot} 号产品位置`;
}

function currentPOS() {
  return currentPosIndex;
}

function activeFoam2DRecipe() {
  return foam2DRecipes.find(item => Number(item.pos) === currentPOS()) || null;
}

function currentDetectionRecipe() {
  return manualSelectedRecipe || activeFoam2DRecipe();
}

async function foamApi(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      'X-CSRFToken': getCsrf(),
      ...(options.body ? {'Content-Type': 'application/json'} : {}),
      ...(options.headers || {}),
    },
  });
  const data = await response.json();
  if (!response.ok || !data.success) throw new Error(data.error || `请求失败（HTTP ${response.status}）`);
  return data;
}

function renderFoamRackProfiles() {
  const host = document.getElementById('foam-rack-profile-list');
  if (!foamRackSpecs.length) {
    host.innerHTML = '<div class="recipe-empty">暂无料架规格，请先新增</div>';
    document.getElementById('foam-rack-actions').hidden = true;
    return;
  }
  host.innerHTML = foamRackSpecs.map(spec => `
    <button type="button" class="foam-profile-item ${Number(spec.id) === Number(selectedFoamRackId) ? 'active' : ''}" onclick="selectFoamRack(${spec.id})">
      <strong>${escape2DHtml(spec.name)}</strong><small>${escape2DHtml(spec.rack_type)} · ${spec.layer_count} 层</small><span class="profile-count">${spec.product_count} 种产品</span>
    </button>`).join('');
  const selected = selectedFoamRack();
  document.getElementById('foam-rack-actions').hidden = !selected;
  document.getElementById('foam-rack-layer-count').textContent = selected?.layer_count || 0;
}

function renderFoamProductProfiles() {
  const host = document.getElementById('foam-product-profile-list');
  if (!selectedFoamRackId) {
    host.innerHTML = '<div class="recipe-empty">请先选择料架规格</div>';
  } else if (!foamProductLayouts.length) {
    host.innerHTML = '<div class="recipe-empty">该料架暂无产品档案，请新增产品</div>';
  } else {
    host.innerHTML = foamProductLayouts.map(layout => `
      <button type="button" class="foam-profile-item ${Number(layout.id) === Number(selectedFoamLayoutId) ? 'active' : ''}" onclick="selectFoamLayout(${layout.id})">
        <strong>${escape2DHtml(layout.product_name || layout.product_code)}</strong><small>${escape2DHtml(layout.product_code)} · 每层 ${layout.qty_per_layer} 个 · 共 ${layout.total_positions} 位</small><span class="profile-count">${layout.configured_count}/${layout.total_positions}</span>
      </button>`).join('');
  }
  const selected = selectedFoamLayout();
  document.getElementById('foam-product-actions').hidden = !selected;
  document.getElementById('foam-product-qty').textContent = selected?.qty_per_layer || 0;
}

function clearFoamMatrix() {
  foam2DRecipes = [];
  foamLayoutLayers = [];
  foamOverflowRecipes = [];
  Object.assign(FOAM_SYSTEM_PROFILE, {rackLayers: 0, productCode: '', productName: '', unitsPerLayer: 0});
  document.getElementById('foam-recipe-list').innerHTML = '<div class="recipe-empty">请选择一个产品档案</div>';
  document.getElementById('foam-current-profile').textContent = '尚未选择产品档案';
  document.getElementById('structure-product-name').textContent = '请选择产品';
  document.getElementById('structure-product-meta').textContent = '每层数量决定横向槽位';
  document.getElementById('structure-recipe-total').textContent = '等待选择档案';
  ['recipe-configured-count','recipe-pending-count','recipe-total-count'].forEach(id => document.getElementById(id).textContent = '0');
}

async function selectFoamRack(rackId, preferredLayoutId = 0) {
  selectedFoamRackId = Number(rackId);
  selectedFoamLayoutId = null;
  renderFoamRackProfiles();
  clearFoamMatrix();
  try {
    const data = await foamApi(API.foamProducts(selectedFoamRackId));
    foamProductLayouts = data.product_layouts || [];
    renderFoamProductProfiles();
    const requested = foamProductLayouts.find(item => Number(item.id) === Number(preferredLayoutId));
    if (requested || foamProductLayouts[0]) await selectFoamLayout((requested || foamProductLayouts[0]).id);
  } catch (error) {
    showToast(error.message, 'error');
  }
}

async function selectFoamLayout(layoutId) {
  selectedFoamLayoutId = Number(layoutId);
  renderFoamProductProfiles();
  try {
    const data = await foamApi(API.foamLayoutRecipes(selectedFoamLayoutId));
    const layout = data.layout;
    const selectedIndex = foamProductLayouts.findIndex(item => Number(item.id) === Number(layout.id));
    if (selectedIndex >= 0) foamProductLayouts[selectedIndex] = layout;
    foamLayoutLayers = data.layers || [];
    foam2DRecipes = foamLayoutLayers.flatMap(layer => layer.slots.map(slot => slot.recipe).filter(Boolean));
    foamCopySources = data.copy_sources || [];
    foamOverflowRecipes = data.overflow_recipes || [];
    Object.assign(FOAM_SYSTEM_PROFILE, {
      rackLayers: layout.layer_count,
      productCode: layout.product_code,
      productName: layout.product_name || layout.product_code,
      unitsPerLayer: layout.qty_per_layer,
    });
    currentPosIndex = Math.min(currentPosIndex, Math.max(layout.total_positions - 1, 0));
    updateFoamProfileContext(layout);
    renderFoamProductProfiles();
    renderRecipeCards();
  } catch (error) {
    showToast(error.message, 'error');
  }
}

function updateFoamProfileContext(layout) {
  const rack = selectedFoamRack();
  document.getElementById('foam-current-profile').textContent = `${rack?.name || layout.rack_spec_name} · ${layout.product_name || layout.product_code}`;
  document.getElementById('structure-rack-name').textContent = rack?.name || layout.rack_spec_name;
  document.getElementById('structure-rack-meta').textContent = `${layout.layer_count} 层 · 类型码 ${layout.rack_type}`;
  document.getElementById('structure-product-name').textContent = `${layout.product_name || layout.product_code} · 每层 ${layout.qty_per_layer} 个`;
  document.getElementById('structure-product-meta').textContent = `${layout.layer_count} × ${layout.qty_per_layer} = ${layout.total_positions} 个装箱位置`;
  document.getElementById('structure-recipe-total').textContent = `${layout.total_positions} 个位置配方`;
  document.getElementById('foam-matrix-title').textContent = `${layout.product_name || layout.product_code} · 位置配方`;
  document.getElementById('recipe-total-count').textContent = layout.total_positions;
  document.getElementById('foam-layout-workbench').href = `/vision/foam-inspector/?mode=foam_recipe&layout_id=${layout.id}`;
  document.getElementById('btn-foam-workbench').href = `/vision/foam-inspector/?mode=foam_recipe&layout_id=${layout.id}`;
  const warning = document.getElementById('foam-overflow-warning');
  warning.hidden = !layout.overflow_count;
  warning.textContent = layout.overflow_count
    ? `当前容量缩小后有 ${layout.overflow_count} 个配方超出范围。数据已完整保留；再次增加层数或每层数量后会自动回到矩阵。`
    : '';
}

// ── 加载三级结构与配方 ──────────────────────────────
async function loadRecipes() {
  try {
    const previousRackId = selectedFoamRackId;
    const previousLayoutId = selectedFoamLayoutId;
    const data = await foamApi(API.foamRackSpecs);
    foamRackSpecs = data.rack_specs || [];
    if (!previousRackId && initialFoamLayoutId) {
      for (const spec of foamRackSpecs) {
        const productData = await foamApi(API.foamProducts(spec.id));
        const requested = (productData.product_layouts || []).find(
          layout => Number(layout.id) === Number(initialFoamLayoutId),
        );
        if (requested) {
          selectedFoamRackId = Number(spec.id);
          foamProductLayouts = productData.product_layouts || [];
          renderFoamRackProfiles();
          renderFoamProductProfiles();
          await selectFoamLayout(requested.id);
          return;
        }
      }
    }
    const initialRack = foamRackSpecs.find(spec => Number(spec.id) === Number(previousRackId))
      || foamRackSpecs.find(spec => spec.product_count > 0)
      || foamRackSpecs[0];
    if (initialRack) await selectFoamRack(initialRack.id, previousLayoutId || initialFoamLayoutId);
    else {
      renderFoamRackProfiles();
      renderFoamProductProfiles();
      clearFoamMatrix();
    }
  } catch (error) {
    console.error('加载配方结构失败：', error);
    showToast(error.message || '网络连接失败', 'error');
  }
}

window.openRackProfileDialog = function(rackId = null) {
  const rack = foamRackSpecs.find(item => Number(item.id) === Number(rackId));
  document.getElementById('foam-rack-profile-modal-title').textContent = rack ? '编辑料架规格' : '新增料架规格';
  document.getElementById('foam-rack-profile-id').value = rack?.id || '';
  document.getElementById('foam-rack-profile-name').value = rack?.name || '';
  document.getElementById('foam-rack-profile-code').value = rack?.rack_type || '';
  document.getElementById('foam-rack-profile-code').disabled = Boolean(rack);
  document.getElementById('foam-rack-profile-layers').value = rack?.layer_count || 3;
  document.getElementById('foam-rack-profile-remark').value = rack?.remark || '';
  document.getElementById('foam-rack-profile-modal').style.display = 'flex';
};

window.openProductProfileDialog = function(layoutId = null) {
  if (!selectedFoamRackId) return showToast('请先选择料架规格', 'info');
  const layout = foamProductLayouts.find(item => Number(item.id) === Number(layoutId));
  document.getElementById('foam-product-profile-modal-title').textContent = layout ? '编辑产品档案' : '新增产品档案';
  document.getElementById('foam-product-profile-id').value = layout?.id || '';
  document.getElementById('foam-product-profile-code').value = layout?.product_code || '';
  document.getElementById('foam-product-profile-code').disabled = Boolean(layout);
  document.getElementById('foam-product-profile-name').value = layout?.product_name || '';
  document.getElementById('foam-product-profile-qty').value = layout?.qty_per_layer || 5;
  document.getElementById('foam-product-profile-modal').style.display = 'flex';
};

window.closeFoamProfileDialogs = function() {
  document.getElementById('foam-rack-profile-modal').style.display = 'none';
  document.getElementById('foam-product-profile-modal').style.display = 'none';
};

window.saveRackProfile = async function() {
  const id = document.getElementById('foam-rack-profile-id').value;
  const payload = {
    name: document.getElementById('foam-rack-profile-name').value.trim(),
    rack_type: document.getElementById('foam-rack-profile-code').value.trim(),
    layer_count: Number(document.getElementById('foam-rack-profile-layers').value),
    remark: document.getElementById('foam-rack-profile-remark').value.trim(),
  };
  try {
    const data = await foamApi(id ? API.foamRackSpec(id) : API.foamRackSpecs, {
      method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload),
    });
    closeFoamProfileDialogs();
    showToast(id ? '料架规格已更新' : '料架规格已新增');
    await loadRecipes();
    if (data.rack_spec) await selectFoamRack(data.rack_spec.id);
  } catch (error) { showToast(error.message, 'error'); }
};

window.saveProductProfile = async function() {
  const id = document.getElementById('foam-product-profile-id').value;
  const payload = {
    product_code: document.getElementById('foam-product-profile-code').value.trim(),
    product_name: document.getElementById('foam-product-profile-name').value.trim(),
    qty_per_layer: Number(document.getElementById('foam-product-profile-qty').value),
  };
  try {
    const data = await foamApi(id ? API.foamProduct(id) : API.foamProducts(selectedFoamRackId), {
      method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload),
    });
    closeFoamProfileDialogs();
    showToast(id ? '产品档案已更新' : '产品档案已新增');
    const products = await foamApi(API.foamProducts(selectedFoamRackId));
    foamProductLayouts = products.product_layouts || [];
    await selectFoamLayout(data.product_layout.id);
  } catch (error) { showToast(error.message, 'error'); }
};

window.changeRackLayers = async function(delta) {
  const rack = selectedFoamRack();
  if (!rack) return;
  const next = rack.layer_count + delta;
  if (next < 1) return showToast('料架至少保留 1 层', 'info');
  try {
    await foamApi(API.foamRackSpec(rack.id), {method:'PATCH', body:JSON.stringify({layer_count: next})});
    rack.layer_count = next;
    document.getElementById('foam-rack-layer-count').textContent = next;
    const products = await foamApi(API.foamProducts(rack.id));
    foamProductLayouts = products.product_layouts || [];
    renderFoamProductProfiles();
    if (selectedFoamLayoutId) await selectFoamLayout(selectedFoamLayoutId);
  } catch (error) { showToast(error.message, 'error'); }
};

window.changeProductQuantity = async function(delta) {
  const layout = selectedFoamLayout();
  if (!layout) return;
  const next = layout.qty_per_layer + delta;
  if (next < 1) return showToast('每层至少保留 1 个产品位置', 'info');
  try {
    await foamApi(API.foamProduct(layout.id), {method:'PATCH', body:JSON.stringify({qty_per_layer: next})});
    await selectFoamRack(selectedFoamRackId, layout.id);
  } catch (error) { showToast(error.message, 'error'); }
};

window.archiveRackProfile = async function() {
  const rack = selectedFoamRack();
  if (!rack || !confirm(`归档料架规格「${rack.name}」？\n关联产品和配方数据会保留。`)) return;
  try {
    const data = await foamApi(API.foamRackSpec(rack.id), {method:'DELETE'});
    showToast(data.message, 'info');
    selectedFoamRackId = null; selectedFoamLayoutId = null;
    await loadRecipes();
  } catch (error) { showToast(error.message, 'error'); }
};

window.archiveProductProfile = async function() {
  const layout = selectedFoamLayout();
  if (!layout || !confirm(`归档产品档案「${layout.product_name || layout.product_code}」？\n位置配方数据会保留。`)) return;
  try {
    const data = await foamApi(API.foamProduct(layout.id), {method:'DELETE'});
    showToast(data.message, 'info');
    selectedFoamLayoutId = null;
    await selectFoamRack(selectedFoamRackId);
  } catch (error) { showToast(error.message, 'error'); }
};

// ── ROI 配置检测辅助函数（支持矩形/多边形/比例坐标三种格式）──
function isRoiConfigured(r) {
  if (!r || typeof r !== 'object') return false;
  if (r.type === 'polygon') return Array.isArray(r.points) && r.points.length >= 3;
  if ('x1r' in r && 'x2r' in r) return r.x2r > r.x1r && r.y2r > r.y1r;
  return (r.width || 0) > 0 && (r.height || 0) > 0;
}
function roiLabel(r) {
  if (!r || typeof r !== 'object') return '⚠️ 未配置';
  if (r.type === 'polygon') return `✅ 多边形(${(r.points || []).length}点)`;
  if ('x1r' in r) return `✅ 比例坐标 [${r.x1r?.toFixed(3)},${r.y1r?.toFixed(3)}→${r.x2r?.toFixed(3)},${r.y2r?.toFixed(3)}]`;
  return `✅ x=${r.x}, y=${r.y}, w=${r.width}, h=${r.height}`;
}

function escape2DHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function thresholdValue(config, keys, fallback) {
  for (const key of keys) {
    if (config?.[key] !== undefined && config[key] !== null) return finiteNumber(config[key], fallback);
  }
  return fallback;
}

function roiPixelGeometry(roi, recipe) {
  if (!roi || typeof roi !== 'object') return {x:0, y:0, width:0, height:0};
  const imageWidth = Math.max(1, finiteNumber(recipe?.image_width, 1));
  const imageHeight = Math.max(1, finiteNumber(recipe?.image_height, 1));
  if (roi.type === 'polygon' && Array.isArray(roi.points) && roi.points.length >= 3) {
    const xs = roi.points.map(point => finiteNumber(point?.[0]) * imageWidth);
    const ys = roi.points.map(point => finiteNumber(point?.[1]) * imageHeight);
    const x = Math.round(Math.min(...xs));
    const y = Math.round(Math.min(...ys));
    return {
      x, y,
      width: Math.max(0, Math.round(Math.max(...xs)) - x),
      height: Math.max(0, Math.round(Math.max(...ys)) - y),
    };
  }
  if (['x1r','y1r','x2r','y2r'].every(key => roi[key] !== undefined)) {
    const x = Math.round(finiteNumber(roi.x1r) * imageWidth);
    const y = Math.round(finiteNumber(roi.y1r) * imageHeight);
    return {
      x, y,
      width: Math.max(0, Math.round(finiteNumber(roi.x2r) * imageWidth) - x),
      height: Math.max(0, Math.round(finiteNumber(roi.y2r) * imageHeight) - y),
    };
  }
  return {
    x: finiteNumber(roi.x),
    y: finiteNumber(roi.y),
    width: finiteNumber(roi.width),
    height: finiteNumber(roi.height),
  };
}

function editedRoiOrOriginal(original, edited, recipe) {
  const current = roiPixelGeometry(original, recipe);
  const unchanged = ['x','y','width','height'].every(key => finiteNumber(edited[key]) === finiteNumber(current[key]));
  return unchanged ? JSON.parse(JSON.stringify(original || {})) : edited;
}

function foamTemplateSideHtml(sideName, sideData) {
  if (!sideData || !finiteNumber(sideData.pixels)) {
    return `<div class="foam-template-side">${sideName}：未保存完整位置数据</div>`;
  }
  const box = sideData.bounding_box || {};
  return `<div class="foam-template-side">${sideName}：面积 ${finiteNumber(sideData.pixels)}px · 中心 (${finiteNumber(sideData.centroid_x).toFixed(1)}, ${finiteNumber(sideData.centroid_y).toFixed(1)}) · 边界框 [${finiteNumber(box.x)}, ${finiteNumber(box.y)}, ${finiteNumber(box.width)}, ${finiteNumber(box.height)}]</div>`;
}

function foamTemplateSummaryHtml(recipe) {
  const status = recipe.standard_template_status || {};
  const sides = status.sides || recipe.standard_template?.sides || {};
  if (!status.ready) {
    return `<div class="foam-template-summary missing"><div class="foam-template-title">⚠️ 标准模板未完成</div><div>${escape2DHtml(status.reason || '请使用合格样件重新示教左右模板')}</div></div>`;
  }
  return `
    <div class="foam-template-summary ready">
      <div class="foam-template-title">✅ 标准模板位置已保存到配方</div>
      ${foamTemplateSideHtml('左侧', sides.left)}
      ${foamTemplateSideHtml('右侧', sides.right)}
      <div class="foam-template-meta">版本 ${escape2DHtml(status.version || recipe.standard_template_version || '—')} · 示教时间 ${escape2DHtml(status.built_at || recipe.standard_template_built_at || '—')}</div>
    </div>`;
}

// ── 渲染配方卡片 ───────────────────────────────────
function renderRecipeCards() {
  if (!selectedFoamLayoutId || !FOAM_SYSTEM_PROFILE.rackLayers || !FOAM_SYSTEM_PROFILE.unitsPerLayer) {
    document.getElementById('foam-recipe-list').innerHTML = '<div class="recipe-empty">请选择一个产品档案</div>';
    return;
  }
  document.getElementById('recipe-current-pos').textContent = currentPOS();
  document.getElementById('recipe-current-location').textContent = positionLabel(currentPOS());
  const list = document.getElementById('foam-recipe-list');
  const currentRecipe = currentDetectionRecipe();
  const recipeByPosition = new Map();
  foam2DRecipes.forEach(recipe => {
    const pos = Number(recipe.pos);
    if (!recipeByPosition.has(pos)) recipeByPosition.set(pos, []);
    recipeByPosition.get(pos).push(recipe);
  });
  const configuredCount = Array.from(recipeByPosition.keys())
    .filter(pos => pos >= 0 && pos < totalFoamPositions()).length;
  document.getElementById('recipe-configured-count').textContent = configuredCount;
  document.getElementById('recipe-pending-count').textContent = totalFoamPositions() - configuredCount;
  document.getElementById('recipe-total-count').textContent = totalFoamPositions();

  const renderConfiguredSlot = (recipe, layer, slot) => {
    const isActive = recipe.id === currentRecipe?.id;
    const roi = recipe.roi_config || {};
    const left = roi.leftFoamROI || {};
    const right = roi.rightFoamROI || {};
    const thresh = recipe.threshold_config || {};
    const hasLeftRoi = isRoiConfigured(left);
    const hasRightRoi = isRoiConfigured(right);

    return `
      <article class="recipe-slot-card configured ${isActive ? 'active' : ''}">
        <div class="slot-card-top">
          <div>
            <h4>${slot} 号产品位置</h4>
            <small>第 ${layer} 层 · POS ${recipe.pos}</small>
          </div>
          <span class="slot-status">${!recipe.is_active ? '已停用 / 草稿' : isActive ? '当前使用' : '已启用'}</span>
        </div>
        <div class="slot-data-name" title="${escape2DHtml(recipe.name)}">数据名称：${escape2DHtml(recipe.name)}</div>
        <div class="slot-roi-state">
          <span class="${hasLeftRoi ? 'ready' : ''}">左 ROI ${hasLeftRoi ? '✓' : '待配置'}</span>
          <span class="${hasRightRoi ? 'ready' : ''}">右 ROI ${hasRightRoi ? '✓' : '待配置'}</span>
        </div>
        <div class="slot-threshold">
          覆盖率 ≥ ${thresholdValue(thresh, ['coverage_threshold','minCoverage'], 0.75)} · 得分 ≥ ${thresholdValue(thresh, ['score_threshold','minScore'], 0.8)}
        </div>
        <details class="slot-details">
          <summary>查看 ROI、模板与版本详情</summary>
          <div class="slot-threshold" style="margin-top:8px;">左 ROI：${hasLeftRoi ? roiLabel(left) : '未配置'}</div>
          <div class="slot-threshold">右 ROI：${hasRightRoi ? roiLabel(right) : '未配置'}</div>
          ${foamTemplateSummaryHtml(recipe)}
        </details>
        <div class="slot-actions">
          <button class="btn btn-sm" onclick="openEditModal(${recipe.id})">编辑</button>
          <a class="btn btn-secondary btn-sm" href="/vision/foam-inspector/?mode=foam_recipe&layout_id=${selectedFoamLayoutId}&recipe_id=${recipe.id}" style="text-decoration:none;">进入工作台</a>
          <button class="btn btn-secondary btn-sm" onclick="copyRecipe(${recipe.id})">复制</button>
          <button class="btn btn-secondary btn-sm slot-delete" onclick="deleteRecipeById(${recipe.id})">删除</button>
        </div>
      </article>`;
  };

  const renderPendingSlot = (pos, layer, slot) => `
      <article class="recipe-slot-card pending">
        <div class="slot-card-top">
          <div>
            <h4>${slot} 号产品位置</h4>
            <small>第 ${layer} 层 · POS ${pos}</small>
          </div>
          <span class="slot-status pending">待配置</span>
        </div>
        <div class="slot-pending-copy">尚未建立该位置的<br>2D 泡棉配方</div>
        <button class="slot-create-button" type="button" onclick="openCreateModalForPosition(${pos})">+ 建立位置配方</button>
      </article>`;

  list.innerHTML = Array.from({length: FOAM_SYSTEM_PROFILE.rackLayers}, (_, layerIndex) => {
    const layer = layerIndex + 1;
    const startPos = layerIndex * FOAM_SYSTEM_PROFILE.unitsPerLayer;
    const configuredInLayer = Array.from({length: FOAM_SYSTEM_PROFILE.unitsPerLayer}, (_, slotIndex) =>
      recipeByPosition.has(startPos + slotIndex)
    ).filter(Boolean).length;
    const slots = Array.from({length: FOAM_SYSTEM_PROFILE.unitsPerLayer}, (_, slotIndex) => {
      const pos = startPos + slotIndex;
      const recipe = recipeByPosition.get(pos);
      return recipe
        ? recipe.map(item => renderConfiguredSlot(item, layer, slotIndex + 1)).join('')
        : renderPendingSlot(pos, layer, slotIndex + 1);
    }).join('');
    return `
      <section class="recipe-layer-section">
        <div class="recipe-layer-head">
          <strong>第 ${layer} 层</strong>
          <span>位置 ${startPos + 1}～${startPos + FOAM_SYSTEM_PROFILE.unitsPerLayer} · 已配置 ${configuredInLayer}/${FOAM_SYSTEM_PROFILE.unitsPerLayer}</span>
        </div>
        <div class="recipe-position-grid">${slots}</div>
      </section>`;
  }).join('');
}

// ── 选择配方编辑（已弃用，保留兼容）───────────────
window.selectRecipeForEdit = function(recipeId) {
  // 此函数已废弃，直接打开编辑弹窗
  openEditModal(recipeId);
};

// ── 打开编辑弹窗 ────────────────────────────────────
window.openEditModal = function(recipeId) {
  const recipe = foam2DRecipes.find(r => r.id === recipeId);
  if (!recipe) return;
  
  const a = recipe?.algorithm_config || {};
  const t = recipe?.threshold_config || {};
  document.getElementById('edit-quality-registration-enabled').checked = a.product_registration?.enabled === true;
  document.getElementById('edit-quality-registration-shift').value = a.product_registration?.max_shift_px ?? 120;
  document.getElementById('edit-quality-registration-rotation').value = a.product_registration?.max_rotation_deg ?? 3;
  document.getElementById('edit-quality-merge-enabled').checked = a.fragment_merge?.enabled === true;
  document.getElementById('edit-quality-merge-gap').value = a.fragment_merge?.max_gap_px ?? 12;
  document.getElementById('edit-quality-merge-color').value = a.fragment_merge?.max_color_distance ?? 25;
  document.getElementById('edit-quality-material').value = a.material_type || 'unspecified';
  document.getElementById('edit-quality-segmentation').value = a.foam_segmentation || 'fixed-threshold';
  document.getElementById('edit-quality-decision-mode').value = t.decision_mode || 'legacy';
  for (const key of ['min_area_ratio', 'max_area_ratio', 'max_missing_ratio', 'max_excess_ratio']) {
    document.getElementById('edit-quality-' + key.replaceAll('_', '-')).value = t[key] ?? '';
  }
  for (const [key, fallback] of Object.entries({pixels_per_mm_x:0, pixels_per_mm_y:0, max_offset_x_mm:2, max_offset_y_mm:2})) {
    document.getElementById('edit-quality-' + key.replaceAll('_', '-')).value = t[key] ?? t[key === 'max_offset_x_mm' ? 'maxOffsetXMm' : 'maxOffsetYMm'] ?? fallback;
  }
  document.getElementById('edit-name').value = recipe.name;
  document.getElementById('edit-remark').value = recipe.remark || '';
  document.getElementById('edit-active').checked = recipe.is_active;

  // 填充弹窗数据
  const roi = recipe.roi_config || {};
  const left = roi.leftFoamROI || {};
  const right = roi.rightFoamROI || {};
  const thresh = recipe.threshold_config || {};
  const leftPixels = roiPixelGeometry(left, recipe);
  const rightPixels = roiPixelGeometry(right, recipe);
  
  document.getElementById('edit-modal-title').textContent = `编辑 ${FOAM_SYSTEM_PROFILE.productName} · ${positionLabel(recipe.pos)}`;
  document.getElementById('edit-modal-id').value = recipe.id;
  document.getElementById('edit-modal-pos').textContent = `${positionLabel(recipe.pos)}（POS ${recipe.pos}）`;
  
  // 左ROI
  document.getElementById('edit-left-x').value = leftPixels.x;
  document.getElementById('edit-left-y').value = leftPixels.y;
  document.getElementById('edit-left-w').value = leftPixels.width;
  document.getElementById('edit-left-h').value = leftPixels.height;
  // 右ROI
  document.getElementById('edit-right-x').value = rightPixels.x;
  document.getElementById('edit-right-y').value = rightPixels.y;
  document.getElementById('edit-right-w').value = rightPixels.width;
  document.getElementById('edit-right-h').value = rightPixels.height;
  // 阈值
  document.getElementById('edit-thresh-cov').value = thresholdValue(thresh, ['coverage_threshold','minCoverage'], 0.75);
  document.getElementById('edit-thresh-score').value = thresholdValue(thresh, ['score_threshold','minScore'], 0.8);
  document.getElementById('edit-thresh-x').value = thresholdValue(thresh, ['max_offset_px','maxOffsetX'], 30);
  document.getElementById('edit-standard-template-data').innerHTML = foamTemplateSummaryHtml(recipe);
  document.getElementById('edit-standard-template-workbench').href = `/vision/foam-inspector/?mode=foam_recipe&layout_id=${selectedFoamLayoutId}&recipe_id=${recipe.id}`;
  
  document.getElementById('recipe-edit-modal').style.display = 'flex';
};

// ── 关闭编辑弹窗 ────────────────────────────────────
window.closeEditModal = function() {
  document.getElementById('recipe-edit-modal').style.display = 'none';
};

// ── 提交编辑弹窗保存 ────────────────────────────────
window.submitEditModal = async function() {
  const recipeId = Number(document.getElementById('edit-modal-id').value);
  const recipe = foam2DRecipes.find(r => r.id === recipeId);
  if (!recipe) {
    showToast('未找到配方，请刷新页面', 'error');
    return;
  }
  
  for (const input of document.querySelectorAll('#recipe-edit-modal input')) {
    if (!input.checkValidity()) { input.reportValidity(); return; }
  }
  if (!document.getElementById('edit-name').value.trim()) { showToast('请输入配方名称', 'error'); return; }
  const editedLeftFoamROI = {
    x: Number(document.getElementById('edit-left-x').value),
    y: Number(document.getElementById('edit-left-y').value),
    width: Number(document.getElementById('edit-left-w').value),
    height: Number(document.getElementById('edit-left-h').value),
  };
  const editedRightFoamROI = {
    x: Number(document.getElementById('edit-right-x').value),
    y: Number(document.getElementById('edit-right-y').value),
    width: Number(document.getElementById('edit-right-w').value),
    height: Number(document.getElementById('edit-right-h').value),
  };
  const leftFoamROI = editedRoiOrOriginal(
    recipe.roi_config?.leftFoamROI,
    editedLeftFoamROI,
    recipe,
  );
  const rightFoamROI = editedRoiOrOriginal(
    recipe.roi_config?.rightFoamROI,
    editedRightFoamROI,
    recipe,
  );
  const coverageThreshold = Number(document.getElementById('edit-thresh-cov').value);
  const scoreThreshold = Number(document.getElementById('edit-thresh-score').value);
  const maxOffsetPx = Number(document.getElementById('edit-thresh-x').value);
  const threshold_config = {
    ...(recipe.threshold_config || {}),
    coverage_threshold: coverageThreshold,
    minCoverage: coverageThreshold,
    score_threshold: scoreThreshold,
    minScore: scoreThreshold,
    max_offset_px: maxOffsetPx,
    maxOffsetX: maxOffsetPx,
    maxOffsetY: maxOffsetPx,
  };
  
  threshold_config.decision_mode = document.getElementById('edit-quality-decision-mode').value;
  for (const key of ['min_area_ratio', 'max_area_ratio', 'max_missing_ratio', 'max_excess_ratio']) {
    const input = document.getElementById('edit-quality-' + key.replaceAll('_', '-'));
    if (input.value === '') {
      threshold_config[key] = null;
      if (threshold_config.decision_mode === 'separated-v2') {
        alert('独立完整性模式需要填写四个完整性门限。');
        return;
      }
    } else {
      if (!input.checkValidity() || !Number.isFinite(Number(input.value))) {
        alert('完整性门限无效，请检查输入。');
        return;
      }
      threshold_config[key] = Number(input.value);
    }
  }

  for (const key of ['pixels_per_mm_x','pixels_per_mm_y','max_offset_x_mm','max_offset_y_mm']) {
    threshold_config[key] = Number(document.getElementById('edit-quality-' + key.replaceAll('_', '-')).value);
  }
  threshold_config.maxOffsetXMm = threshold_config.max_offset_x_mm;
  threshold_config.maxOffsetYMm = threshold_config.max_offset_y_mm;
  if (document.getElementById('edit-quality-registration-enabled').checked && (recipe.roi_config?.productAnchorROIs || []).length < 2) {
    showToast('请先在示教工作台绘制两个产品本体基准区', 'error'); return;
  }
  try {
    const res = await fetch(API.saveRecipe, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: recipe.id,
        layout_id: selectedFoamLayoutId,
        pos: recipe.pos,
        name: document.getElementById('edit-name').value.trim(),
        camera_side: recipe.camera_side,
        image_width: recipe.image_width,
        image_height: recipe.image_height,
        roi_config: { ...(recipe.roi_config || {}), leftFoamROI, rightFoamROI },
        threshold_config,
    algorithm_config: {
      material_type: document.getElementById('edit-quality-material').value,
      foam_segmentation: document.getElementById('edit-quality-segmentation').value,
      product_registration: {
        ...(recipe?.algorithm_config?.product_registration || {}),
        enabled: document.getElementById('edit-quality-registration-enabled').checked,
        max_shift_px: Number(document.getElementById('edit-quality-registration-shift').value),
        max_rotation_deg: Number(document.getElementById('edit-quality-registration-rotation').value),
      },
      fragment_merge: {
        ...(recipe?.algorithm_config?.fragment_merge || {}),
        enabled: document.getElementById('edit-quality-merge-enabled').checked,
        max_gap_px: Number(document.getElementById('edit-quality-merge-gap').value),
        max_color_distance: Number(document.getElementById('edit-quality-merge-color').value),
      },
    },
        is_active: document.getElementById('edit-active').checked,
        remark: document.getElementById('edit-remark').value.trim(),
      }),
    });
    const data = await res.json();
    if (data.success) {
      showToast('配方保存成功', 'success');
      closeEditModal();
      await loadRecipes();
    } else {
      showToast(data.error || '保存失败', 'error');
    }
  } catch (e) {
    showToast('网络请求失败：' + e.message, 'error');
  }
};

// ── 新增配方 ────────────────────────────────────────
window.openCreateModal = function() {
  // 如果当前在3D配方标签页，打开3D Modal
  if (currentTab === 'rack3d') {
    openRackMasterModal();
    return;
  }
  if (!selectedFoamLayoutId) {
    showToast('请先选择料架规格和产品档案', 'info');
    return;
  }
  
  // 2D配方的新增逻辑
  modalMode = 'create';
  editingRecipeId = null;
  document.getElementById('modal-title').textContent = '新增配方';
  document.getElementById('modal-name').value = '';
  document.getElementById('modal-pos').value = '';
  document.getElementById('modal-remark').value = '';
  renderCopySourceOptions();
  updateModalPositionPreview();
  document.getElementById('recipe-modal').style.display = 'flex';
};

window.openCreateModalForPosition = function(pos) {
  openCreateModal();
  const meta = positionMeta(pos);
  document.getElementById('modal-title').textContent = `新增 ${positionLabel(pos)} 配方`;
  document.getElementById('modal-name').value = `${FOAM_SYSTEM_PROFILE.productCode}产品-L${meta.layer}-P${String(meta.slot).padStart(2, '0')} 泡棉配方`;
  document.getElementById('modal-pos').value = String(pos);
  updateModalPositionPreview();
};

function renderCopySourceOptions(selectedId = '') {
  const select = document.getElementById('modal-copy-source');
  select.replaceChildren(new Option('不复制，使用默认参数', ''));
  foamCopySources.forEach(source => {
    select.add(new Option(
      `${source.rack_name} / ${source.product_name} / POS ${source.pos} · ${source.name}`,
      String(source.id),
    ));
  });
  select.value = selectedId ? String(selectedId) : '';
}

function updateModalPositionPreview() {
  const input = document.getElementById('modal-pos');
  const preview = document.getElementById('modal-position-preview');
  if (!input || !preview) return;
  const value = input.value.trim();
  if (value === '') {
    preview.textContent = `POS 从 0 开始；当前产品可使用 POS 0～${Math.max(totalFoamPositions() - 1, 0)}`;
    return;
  }
  const pos = Number(value);
  if (!Number.isInteger(pos) || pos < 0 || pos >= totalFoamPositions()) {
    preview.textContent = `超出当前产品的有效范围（POS 0～${Math.max(totalFoamPositions() - 1, 0)}）`;
    return;
  }
  preview.textContent = `将映射到：${positionLabel(pos)} · 全料架第 ${pos + 1} 个产品`;
}

// ── 复制配方 ────────────────────────────────────────
window.copyRecipe = function(recipeId) {
  const recipe = foam2DRecipes.find(r => r.id === recipeId);
  if (!recipe) return;
  
  modalMode = 'create';
  editingRecipeId = null;
  document.getElementById('modal-title').textContent = '复制配方';
  document.getElementById('modal-name').value = recipe.name + ' (副本)';
  document.getElementById('modal-pos').value = '';
  document.getElementById('modal-remark').value = recipe.remark || '';
  renderCopySourceOptions(recipe.id);
  updateModalPositionPreview();
  document.getElementById('recipe-modal').style.display = 'flex';
};

// ── 删除配方 ────────────────────────────────────────
window.deleteRecipeById = function(recipeId) {
  const recipe = foam2DRecipes.find(r => r.id === recipeId);
  if (recipe) deleteRecipe(recipeId, recipe.name);
};

window.deleteRecipe = async function(recipeId, recipeName) {
  if (!confirm(`确定要删除配方「${recipeName}」吗？\n\n此操作无法撤销！`)) return;
  
  try {
    const res = await fetch(API.deleteRecipe(recipeId), {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() },
    });
    const data = await res.json();
    if (data.success) {
      showToast('配方删除成功', 'success');
      await loadRecipes();
    } else {
      showToast(data.error || '删除失败', 'error');
    }
  } catch (e) {
    showToast('网络请求失败：' + e.message, 'error');
  }
};

// ── 关闭弹窗 ────────────────────────────────────────
window.closeModal = function() {
  document.getElementById('recipe-modal').style.display = 'none';
};

// ── 提交弹窗 ────────────────────────────────────────
window.submitModal = async function() {
  const name = document.getElementById('modal-name').value.trim();
  const pos = document.getElementById('modal-pos').value.trim();
  const remark = document.getElementById('modal-remark').value.trim();
  const sourceRecipeId = document.getElementById('modal-copy-source').value;
  
  if (!name) {
    showToast('请输入配方名称', 'error');
    return;
  }
  
  if (pos === '' || Number(pos) < 0 || Number(pos) >= totalFoamPositions()) {
    showToast(`请输入有效的 POS 位置（当前为 0～${Math.max(totalFoamPositions() - 1, 0)}）`, 'error');
    return;
  }
  
  try {
    const res = await fetch(API.createRecipe, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        layout_id: selectedFoamLayoutId,
        pos: parseInt(pos),
        source_recipe_id: sourceRecipeId || null,
        remark: remark,
      }),
    });
    const data = await res.json();
    if (data.success) {
      showToast('配方创建成功', 'success');
      closeModal();
      await loadRecipes();
    } else {
      showToast(data.error || '创建失败', 'error');
    }
  } catch (e) {
    showToast('网络请求失败：' + e.message, 'error');
  }
};

// ── 标签页切换 ──────────────────────────────────────
let currentTab = 'foam2d'; // 当前激活的标签页

document.querySelectorAll('.recipe-tab[data-recipe-tab]').forEach(tab => {
  tab.addEventListener('click', () => {
    const tabName = tab.dataset.recipeTab;

    // 切换激活状态
    document.querySelectorAll('.recipe-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');

    // 切换显示内容（带淡入动画）
    document.querySelectorAll('.recipe-tab-section').forEach(section => {
      section.classList.remove('tab-active');
      section.style.display = 'none';
    });
    const activeSection = document.getElementById(`recipe-tab-${tabName}`);
    if (activeSection) {
      activeSection.style.display = '';
      requestAnimationFrame(() => activeSection.classList.add('tab-active'));
    }

    currentTab = tabName;
    updateWorkbenchButtons(tabName);

    if (tabName === 'rack3d') load3DRecipes();
  });
});


// ── 更新工作台按钮显示 ─────────────────────────────
function updateWorkbenchButtons(tabName) {
  const foamBtn = document.getElementById('btn-foam-workbench');
  const rackBtn = document.getElementById('btn-rack-workbench');
  const createBtn = document.getElementById('btn-create-recipe');
  
  if (tabName === 'foam2d') {
    // 2D配方标签页：显示泡棉检测工作台
    if(foamBtn) foamBtn.style.display = '';
    if(rackBtn) rackBtn.style.display = 'none';
    if(createBtn) createBtn.style.display = '';
    if(createBtn) createBtn.textContent = '新增位置配方';
  } else if (tabName === 'rack3d') {
    // 3D配方标签页：显示料架定位工作台
    if(foamBtn) foamBtn.style.display = 'none';
    if(rackBtn) rackBtn.style.display = '';
    if(createBtn) createBtn.style.display = 'none';
  } else {
    if(foamBtn) foamBtn.style.display = 'none';
    if(rackBtn) rackBtn.style.display = 'none';
    if(createBtn) createBtn.style.display = 'none';
  }
}

// ============================================================
//  3D配方管理逻辑
// ============================================================
let rack3DRecipes = [];
let rackMasterRecipes = [];
let selectedRackMasterId = null;
let currentRackScene = 'basic';

function escape3DHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function selectedRackMasterRecipe() {
  return rackMasterRecipes.find(item => item.id === selectedRackMasterId) || null;
}

async function loadRackMasterRecipes() {
  try {
    const response = await fetch(API.rackMasterRecipes);
    const data = await response.json();
    if (!data.success) throw new Error(data.error || '读取失败');
    rackMasterRecipes = data.recipes || [];
    if (!rackMasterRecipes.some(item => item.id === selectedRackMasterId)) {
      selectedRackMasterId = rackMasterRecipes[0]?.id || null;
    }
    renderRackMasterList();
    renderRackMasterDetail();
  } catch (error) {
    const select = document.getElementById('rack-master-select');
    if (select) select.innerHTML = `<option>读取失败：${escape3DHtml(error.message)}</option>`;
    const target = document.getElementById('rack-master-detail');
    if (target) target.innerHTML = `<div class="rack-master-empty">读取失败：${escape3DHtml(error.message)}</div>`;
    showToast('料架主配方读取失败：' + error.message, 'error');
  }
}

function renderRackMasterList() {
  const target = document.getElementById('rack-master-select');
  const status = document.getElementById('rack-master-status');
  if (!target) return;
  if (!rackMasterRecipes.length) {
    target.innerHTML = '<option value="">暂无料架主配方</option>';
    if (status) status.innerHTML = '<strong>尚未配置</strong>请先新增一份料架主配方';
    return;
  }
  target.innerHTML = rackMasterRecipes.map(recipe => `<option value="${recipe.id}" ${recipe.id === selectedRackMasterId ? 'selected' : ''}>${escape3DHtml(recipe.recipe_code)} · ${escape3DHtml(recipe.name)} · ${escape3DHtml(recipe.product_code || '未关联产品')}</option>`).join('');
  const recipe = selectedRackMasterRecipe();
  const validation = recipe?.validation || {};
  if (status && recipe) {
    const state = validation.production_ready ? '生产就绪' : '需要完善配置';
    status.innerHTML = `<strong>${state}</strong>${recipe.layer_count}层 × ${recipe.quantity_per_layer}件 · ${validation.mapping_ready_count || 0}/${validation.mapping_total_count || 0} 层位就绪`;
  }
}

window.selectRackMasterRecipe = function(id) {
  selectedRackMasterId = id;
  renderRackMasterList();
  renderRackMasterDetail();
};

window.selectRackWorkflowScene = function(scene) {
  currentRackScene = scene;
  document.querySelectorAll('[data-rack-scene]').forEach(button => {
    button.classList.toggle('active', button.dataset.rackScene === scene);
  });
  renderRackMasterDetail();
};

function renderRackLayout(recipe) {
  const layers = Math.max(0, Number(recipe.layer_count) || 0);
  const slots = Math.max(0, Number(recipe.quantity_per_layer) || 0);
  if (!layers || !slots) return '<div class="rack-master-empty">请先设置层数和每层件数</div>';
  const topDown = String(recipe.loading_direction).startsWith('TOP_DOWN');
  const rightLeft = String(recipe.loading_direction).endsWith('RIGHT_LEFT');
  const layerNumbers = Array.from({length: layers}, (_, index) => layers - index);
  return `<div class="rack-layout-preview">${layerNumbers.map(layerNo => {
    const logicalLayer = topDown ? layers - layerNo + 1 : layerNo;
    const positions = Array.from({length: slots}, (_, index) => {
      const logicalSlot = rightLeft ? slots - index : index + 1;
      const order = (logicalLayer - 1) * slots + logicalSlot;
      return `<div class="rack-layout-slot" title="装箱顺序 ${order}">${order}</div>`;
    });
    return `<div class="rack-layout-row"><div class="rack-layout-layer">第 ${layerNo} 层</div><div class="rack-layout-slots" style="--slot-count:${slots}">${positions.join('')}</div></div>`;
  }).join('')}</div>`;
}

function rackVisionOptions(mapping, rackType) {
  const selectedId = Number(mapping.rack_location_recipe_id || 0);
  const options = rack3DRecipes.map(recipe => {
    const mismatch = (recipe.position_no !== mapping.station_position_no || recipe.layer_no !== mapping.layer_no);
    const typeHint = recipe.rack_type && rackType && recipe.rack_type !== rackType ? ` · ${recipe.rack_type}` : '';
    return `<option value="${recipe.id}" ${recipe.id === selectedId ? 'selected' : ''}>${escape3DHtml(recipe.recipe_name)} · P${recipe.position_no}/L${recipe.layer_no}${mismatch ? '（层位不同）' : ''}${escape3DHtml(typeHint)}</option>`;
  });
  return `<option value="">待选择</option>${options.join('')}`;
}

function rackSceneHeader(sectionCode, title, description, recipe, actionHtml = '') {
  return `<div class="rack-scene-head"><div><span class="rack-scene-tag">${sectionCode} · ${escape3DHtml(recipe.recipe_code)} · V${recipe.version}</span><h3>${title}</h3><p>${description}</p></div><div class="rack-flow-actions">${actionHtml}</div></div>`;
}

function renderRackBasicScene(recipe) {
  const validation = recipe.validation || {};
  return `${rackSceneHeader('RECIPE 01', '基础与 MES 配方参数', '这里仅维护料框、产品和装箱工艺参数，不显示生产运行状态。', recipe, '<button class="btn btn-sm" onclick="openRackMasterModal(selectedRackMasterId)">编辑基础参数</button>')}
    <div class="rack-scene-body">
      <div class="rack-master-badges"><span class="rack-master-badge ${recipe.is_active ? 'ok' : 'error'}">${recipe.is_active ? '已启用' : '已停用'}</span><span class="rack-master-badge ${validation.valid ? 'ok' : 'error'}">${validation.valid ? '基础参数有效' : '基础参数待完善'}</span><span class="rack-master-badge">${escape3DHtml(recipe.loading_direction_label)}</span><span class="rack-master-badge">${escape3DHtml(recipe.full_condition_label)}</span></div>
      <div class="rack-flow-grid">
        <article class="rack-flow-card" style="padding-left:16px;"><h4>配方身份</h4><p>MES 与本地数据库用于识别这份料架装箱配方的关键字段。</p><div class="rack-flow-values"><span class="rack-flow-value"><strong>配方编码</strong> ${escape3DHtml(recipe.recipe_code)}</span><span class="rack-flow-value"><strong>名称</strong> ${escape3DHtml(recipe.name)}</span><span class="rack-flow-value"><strong>产品</strong> ${escape3DHtml(recipe.product_code || '未关联')}</span><span class="rack-flow-value"><strong>料架类型</strong> ${escape3DHtml(recipe.rack_type || '未配置')}</span></div></article>
        <article class="rack-flow-card" style="padding-left:16px;"><h4>装箱结构</h4><p>定义层数、每层件数、工位数量和整框容量。</p><div class="rack-flow-values"><span class="rack-flow-value"><strong>工位</strong> ${recipe.station_position_count} 个</span><span class="rack-flow-value"><strong>层数</strong> ${recipe.layer_count} 层</span><span class="rack-flow-value"><strong>每层</strong> ${recipe.quantity_per_layer} 件</span><span class="rack-flow-value"><strong>总数量</strong> ${recipe.total_quantity} 件</span></div></article>
        <article class="rack-flow-card" style="padding-left:16px;"><h4>MES 尺寸参数</h4><p>用于与 2D/3D 实测结果进行配方比对。</p><div class="rack-flow-values"><span class="rack-flow-value"><strong>层高</strong> ${format3DNumber(recipe.layer_height)} mm</span><span class="rack-flow-value"><strong>层距</strong> ${format3DNumber(recipe.layer_spacing)} mm</span></div></article>
        <article class="rack-flow-card" style="padding-left:16px;"><h4>允许偏差</h4><p>视觉实测与 MES 理论值的放行范围。</p><div class="rack-flow-values"><span class="rack-flow-value"><strong>ΔX</strong> ±${format3DNumber(recipe.tolerance_x)} mm</span><span class="rack-flow-value"><strong>ΔY</strong> ±${format3DNumber(recipe.tolerance_y)} mm</span><span class="rack-flow-value"><strong>ΔZ</strong> ±${format3DNumber(recipe.tolerance_z)} mm</span></div></article>
        <article class="rack-flow-card wide" style="padding-left:16px;min-height:0;"><details><summary style="cursor:pointer;font-weight:800;color:#334155;">装箱位置预览 · ${escape3DHtml(recipe.loading_direction_label)}</summary><div style="margin-top:12px;">${renderRackLayout(recipe)}</div></details></article>
      </div>
    </div>`;
}

function renderRackPositionRecipeScene(recipe, positionNo) {
  if (positionNo > recipe.station_position_count) {
    return `${rackSceneHeader(`RECIPE 0${positionNo + 1}`, `${positionNo}号位定位配方`, '当前主配方尚未启用该工位。', recipe, '<button class="btn btn-sm" onclick="openRackMasterModal(selectedRackMasterId)">启用2号位</button>')}<div class="rack-master-empty">请在基础参数中把“工位位置数”改为 2，然后再配置2号位各层定位配方。</div>`;
  }
  const mappings = (recipe.mappings || []).filter(mapping => mapping.station_position_no === positionNo);
  const readyCount = mappings.filter(mapping => mapping.ready).length;
  const cards = mappings.map(mapping => {
    const stateClass = mapping.ready ? 'ok' : mapping.rack_location_recipe_id ? 'warn' : 'error';
    const stateText = mapping.ready ? '已就绪' : mapping.rack_location_recipe_id ? '配方待完善' : '未选择';
    const issues = (mapping.issues || []).join('、');
    return `<div class="rack-mapping-card"><div class="rack-mapping-card-head"><strong>第 ${mapping.layer_no} 层</strong><span class="rack-master-badge ${stateClass}" title="${escape3DHtml(issues)}">${stateText}</span></div><label style="font-size:12px;color:#64748b;">3D 定位配方</label><select id="rack-map-recipe-${positionNo}-${mapping.layer_no}">${rackVisionOptions(mapping, recipe.rack_type)}</select><label style="display:block;margin-top:8px;font-size:12px;color:#64748b;">机器人目标位</label><input id="rack-map-target-${positionNo}-${mapping.layer_no}" value="${escape3DHtml(mapping.robot_target_code || '')}" placeholder="ROBOT_P${positionNo}_L${mapping.layer_no}"><button class="btn btn-secondary btn-sm" onclick="saveRackMapping(${positionNo}, ${mapping.layer_no})">保存第 ${mapping.layer_no} 层</button></div>`;
  }).join('');
  return `${rackSceneHeader(`RECIPE 0${positionNo + 1}`, `${positionNo}号位 · 分层定位配方`, `为${positionNo}号位的每一层选择独立 3D 定位配方和机器人目标位。`, recipe, '<a href="/vision/rack-locator/" class="btn btn-secondary btn-sm">3D 示教工作台</a><button class="btn btn-sm" onclick="create3DRecipe()">新增3D配方</button>')}
    <div class="rack-scene-body"><div class="rack-loop-banner"><div><strong>${positionNo}号位：${readyCount}/${recipe.layer_count} 层已就绪</strong><br><span>配方映射只建立引用，不会修改原有 3D ROI、模板或标定数据。</span></div><span>${escape3DHtml(recipe.rack_type)}</span></div><div class="rack-mapping-cards">${cards || '<div class="rack-master-empty">暂无可配置层，请先设置层数。</div>'}</div>${recipe.layer_count > 3 ? '<div class="rack-scene-note">现有 3D 定位算法仅支持第1～3层；第4层及以上数据会保留，但不能标记为生产就绪。</div>' : ''}</div>`;
}

function renderRackInspectionScene(recipe) {
  return `${rackSceneHeader('RECIPE 04', '检测配方与装箱规则', '集中查看这份料架配方关联的空箱、泡棉和装箱规则入口。', recipe)}
    <div class="rack-scene-body"><div class="rack-flow-grid">
      <article class="rack-flow-card" style="padding-left:16px;"><h4>2D 空箱检测配方</h4><p>管理空箱 ROI、判定参数和层数检查。主配方期望层数：${recipe.layer_count} 层。</p><div class="rack-flow-actions"><a href="/vision/foam-inspector/?mode=empty_rack" class="btn btn-sm">编辑空箱配方</a><a href="/vision/recipes/?tab=empty2d" class="btn btn-secondary btn-sm">查看配方摘要</a></div></article>
      <article class="rack-flow-card" style="padding-left:16px;"><h4>2D 泡棉检测配方</h4><p>本料架共 ${recipe.total_quantity} 个装箱位置；泡棉工作台按产品位置维护检测 ROI 和阈值。</p><div class="rack-flow-actions"><a href="/vision/foam-inspector/?mode=foam_recipe" class="btn btn-sm">编辑泡棉配方</a><a href="/vision/recipes/?tab=foam2d" class="btn btn-secondary btn-sm">查看位置配方</a></div></article>
      <article class="rack-flow-card" style="padding-left:16px;"><h4>装箱顺序</h4><p>根据已完成数量计算当前层、当前件和下一装箱位置。</p><div class="rack-flow-values"><span class="rack-flow-value"><strong>方向</strong> ${escape3DHtml(recipe.loading_direction_label)}</span><span class="rack-flow-value"><strong>每层</strong> ${recipe.quantity_per_layer} 件</span></div></article>
      <article class="rack-flow-card" style="padding-left:16px;"><h4>满框条件</h4><p>定义装箱循环何时结束并进入整框上传。</p><div class="rack-flow-values"><span class="rack-flow-value"><strong>条件</strong> ${escape3DHtml(recipe.full_condition_label)}</span><span class="rack-flow-value"><strong>计划数量</strong> ${recipe.total_quantity} 件</span></div><div class="rack-flow-actions"><button class="btn btn-secondary btn-sm" onclick="openRackMasterModal(selectedRackMasterId)">编辑装箱规则</button></div></article>
    </div><div class="rack-scene-note">该页只管理配方。PLC 握手、报警锁站、MES 上传和断电补传属于运行流程，不在这里操作。</div></div>`;
}

function renderRackMasterDetail() {
  const target = document.getElementById('rack-master-detail');
  if (!target) return;
  const recipe = selectedRackMasterRecipe();
  if (!recipe) {
    target.innerHTML = '<div class="rack-master-empty">请先新增或选择一份料架主配方。</div>';
    return;
  }
  const renderers = {
    basic: renderRackBasicScene,
    position1: recipeValue => renderRackPositionRecipeScene(recipeValue, 1),
    position2: recipeValue => renderRackPositionRecipeScene(recipeValue, 2),
    inspection: renderRackInspectionScene,
  };
  target.innerHTML = (renderers[currentRackScene] || renderRackBasicScene)(recipe);
}

window.openRackMasterModal = function(id = null) {
  const recipe = rackMasterRecipes.find(item => item.id === Number(id)) || null;
  document.getElementById('rack-master-modal-title').textContent = recipe ? '编辑料架主配方' : '新增料架主配方';
  document.getElementById('rack-master-id').value = recipe?.id || '';
  document.getElementById('rack-master-code').value = recipe?.recipe_code || '';
  document.getElementById('rack-master-name').value = recipe?.name || '';
  document.getElementById('rack-master-product').value = recipe?.product_code || '';
  document.getElementById('rack-master-type').value = recipe?.rack_type || '';
  document.getElementById('rack-master-position-count').value = recipe?.station_position_count || 2;
  document.getElementById('rack-master-layers').value = recipe?.layer_count || 3;
  document.getElementById('rack-master-per-layer').value = recipe?.quantity_per_layer || 5;
  document.getElementById('rack-master-total').value = recipe?.total_quantity || 15;
  document.getElementById('rack-master-height').value = recipe?.layer_height || 0;
  document.getElementById('rack-master-spacing').value = recipe?.layer_spacing || 0;
  document.getElementById('rack-master-tol-x').value = recipe?.tolerance_x || 0;
  document.getElementById('rack-master-tol-y').value = recipe?.tolerance_y || 0;
  document.getElementById('rack-master-tol-z').value = recipe?.tolerance_z || 0;
  document.getElementById('rack-master-direction').value = recipe?.loading_direction || 'BOTTOM_UP_LEFT_RIGHT';
  document.getElementById('rack-master-full').value = recipe?.full_condition || 'QUANTITY_REACHED';
  document.getElementById('rack-master-active').checked = recipe?.is_active ?? true;
  document.getElementById('rack-master-modal').style.display = 'flex';
};

window.closeRackMasterModal = function() {
  document.getElementById('rack-master-modal').style.display = 'none';
};

window.saveRackMasterRecipe = async function() {
  const id = document.getElementById('rack-master-id').value;
  const payload = {
    id: id || undefined,
    recipe_code: document.getElementById('rack-master-code').value.trim(),
    name: document.getElementById('rack-master-name').value.trim(),
    product_code: document.getElementById('rack-master-product').value.trim(),
    rack_type: document.getElementById('rack-master-type').value.trim(),
    station_position_count: Number(document.getElementById('rack-master-position-count').value),
    layer_count: Number(document.getElementById('rack-master-layers').value),
    quantity_per_layer: Number(document.getElementById('rack-master-per-layer').value),
    total_quantity: Number(document.getElementById('rack-master-total').value),
    layer_height: Number(document.getElementById('rack-master-height').value),
    layer_spacing: Number(document.getElementById('rack-master-spacing').value),
    tolerance_x: Number(document.getElementById('rack-master-tol-x').value),
    tolerance_y: Number(document.getElementById('rack-master-tol-y').value),
    tolerance_z: Number(document.getElementById('rack-master-tol-z').value),
    loading_direction: document.getElementById('rack-master-direction').value,
    full_condition: document.getElementById('rack-master-full').value,
    is_active: document.getElementById('rack-master-active').checked,
  };
  if (!payload.recipe_code || !payload.name || !payload.rack_type) return showToast('配方编码、名称和料架类型不能为空', 'error');
  try {
    const response = await fetch(API.rackMasterRecipes, {method: id ? 'PATCH' : 'POST', headers: {'X-CSRFToken': getCsrf(), 'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    const data = await response.json();
    if (!data.success) throw new Error(data.error || '保存失败');
    selectedRackMasterId = data.recipe.id;
    closeRackMasterModal();
    await loadRackMasterRecipes();
    showToast(data.message || '料架主配方已保存', 'success');
  } catch (error) { showToast('保存失败：' + error.message, 'error'); }
};

window.saveRackMapping = async function(positionNo, layerNo) {
  const recipe = selectedRackMasterRecipe();
  if (!recipe) return;
  const payload = {rack_recipe_id: recipe.id, station_position_no: positionNo, layer_no: layerNo, rack_location_recipe_id: document.getElementById(`rack-map-recipe-${positionNo}-${layerNo}`).value || null, robot_target_code: document.getElementById(`rack-map-target-${positionNo}-${layerNo}`).value.trim(), enabled: true};
  try {
    const response = await fetch(API.rackMasterMappingSave, {method: 'POST', headers: {'X-CSRFToken': getCsrf(), 'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    const data = await response.json();
    if (!data.success) throw new Error(data.error || '保存失败');
    await loadRackMasterRecipes();
    showToast(data.message || '映射已保存', 'success');
  } catch (error) { showToast('映射保存失败：' + error.message, 'error'); }
};

window.validateRackMasterRecipe = async function() {
  const recipe = selectedRackMasterRecipe();
  if (!recipe) return;
  const response = await fetch(API.rackMasterValidate(recipe.id));
  const data = await response.json();
  if (!data.success) return showToast(data.error || '检查失败', 'error');
  const validation = data.validation;
  showToast(validation.production_ready ? '主配方和视觉映射均已生产就绪' : `检查完成：${validation.errors.length} 个结构问题，${validation.warnings.length} 个视觉提醒`, validation.production_ready ? 'success' : 'info', 3500);
};

window.resolveRackPosition = async function() {
  const recipe = selectedRackMasterRecipe();
  if (!recipe) return;
  const completed = Number(document.getElementById('rack-resolve-completed').value || 0);
  const position = Number(document.getElementById('rack-resolve-position').value || 1);
  const target = document.getElementById('rack-resolver-result');
  try {
    const response = await fetch(`${API.rackMasterResolve(recipe.id)}?completed_quantity=${completed}&station_position_no=${position}`);
    const data = await response.json();
    if (!data.success) throw new Error(data.error || '计算失败');
    const result = data.resolution;
    if (result.is_full) {
      target.textContent = `已满框：${result.completed_quantity}/${result.planned_quantity}`;
    } else {
      const mapping = result.mapping;
      const next = result.next ? `；下一位置：第${result.next.layer_no}层第${result.next.slot_no}件` : '；本件完成后满框';
      target.textContent = `当前：第${result.current.layer_no}层第${result.current.slot_no}件${next}；3D配方：${mapping?.rack_location_recipe_name || '未映射'}`;
    }
  } catch (error) { target.textContent = '计算失败：' + error.message; }
};

function format3DNumber(value, digits = 3) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return Number.isInteger(number) ? String(number) : number.toFixed(digits).replace(/0+$/, '').replace(/\.$/, '');
}

function formatPixelRoi(roi) {
  if (!roi || !['x', 'y', 'w', 'h'].every(key => Number.isFinite(Number(roi[key])))) {
    return '<span class="rack3d-template-empty">未框选</span>';
  }
  return `x=${format3DNumber(roi.x)} y=${format3DNumber(roi.y)} w=${format3DNumber(roi.w)} h=${format3DNumber(roi.h)}`;
}

function formatTemplatePlane(label, plane) {
  if (!plane) return `${label}：—`;
  const normal = Array.isArray(plane.normal) ? plane.normal : [];
  const normalText = [0, 1, 2].map(index => format3DNumber(normal[index], 4)).join(', ');
  const offset = plane.offset ?? plane.d;
  const inlier = Number.isFinite(Number(plane.inlier_ratio))
    ? `${(Number(plane.inlier_ratio) * 100).toFixed(1)}%`
    : '—';
  return `${label} N=[${normalText}] D=${format3DNumber(offset, 3)} 内点率=${inlier} 点数=${format3DNumber(plane.point_count)}`;
}

function render3DWorkbenchData(recipe) {
  const roiConfig = recipe?.roi_config || {};
  const rois = roiConfig.cloud_match_config?.rois || [];
  const reference = roiConfig.cloud_match_reference;
  const measurement = reference?.measurement;
  const valid = measurement?.success && measurement.coordinateSystem === 'camera' && measurement.unit === 'mm';
  const labels = [['P1_horizontal', 'ROI1 · P1 横杆'], ['P1_vertical', 'ROI2 · P1 立柱'],
                  ['P2_horizontal', 'ROI3 · P2 横杆'], ['P2_vertical', 'ROI4 · P2 立柱']];
  const templateRows = ['P1', 'P2'].map(name => {
    const point = valid ? measurement.points?.find(item => item.name === name && item.success) : null;
    const coords = point?.xyz;
    const text = Array.isArray(coords) && coords.length === 3 && coords.every(Number.isFinite)
      ? coords.map(value => format3DNumber(value)).join(' / ') : '—';
    return `<div class="rack3d-template-detail">${name}：${text}</div>`;
  }).join('');
  return `
    <div class="rack3d-data-block">
      <div class="rack3d-data-title">四个 ROI 框（2D 原图像素）</div>
      <div class="rack3d-roi-grid">${labels.map(([target, label]) => {
        const roi = rois.find(item => item.target === target);
        return `<div class="rack3d-roi-item">${label}：${formatPixelRoi(roi ? {...roi, w: roi.width ?? roi.w, h: roi.height ?? roi.h} : null)}</div>`;
      }).join('')}</div>
    </div>
    <div class="rack3d-data-block">
      <div class="rack3d-data-title">点云标准模板参考点（相机原始 X / Y / Z · mm）</div>
      ${valid ? '<div class="rack3d-template-ok">✔ 已保存标准模板</div>' : '<div class="rack3d-template-empty">尚未示教，标准模板为空。</div>'}
      ${templateRows}
      ${reference?.taught_at ? `<div class="rack3d-template-detail">保存时间：${escape3DHtml(new Date(reference.taught_at).toLocaleString('zh-CN', {hour12:false}))}</div>` : ''}
    </div>
  `;
}

function update3DModalWorkbenchData(recipe) {
  const target = document.getElementById('modal-3d-workbench-data');
  if (target) target.innerHTML = render3DWorkbenchData(recipe || {});
}

// ── 加载3D配方 ──────────────────────────────────────
async function load3DRecipes() {
  try {
    const res = await fetch('/vision/api/vision/3d/recipes/');
    const data = await res.json();
    if (data.success) {
      rack3DRecipes = data.recipes || data.data?.recipes || [];
      render3DRecipeCards();
      renderRackMasterDetail();
    } else {
      showToast('加载3D配方失败', 'error');
    }
  } catch (e) {
    console.error('加载3D配方失败：', e);
    showToast('网络连接失败', 'error');
  }
}

// ── 渲染3D配方卡片 ─────────────────────────────────
function render3DRecipeCards() {
  const list = document.getElementById('rack3d-recipe-list');
  
  if (!rack3DRecipes.length) {
    list.innerHTML = `
      <div class="recipe-empty">
        <div>暂无 3D 配方数据，请先建立一份基础配方。</div>
        <button class="btn btn-sm" type="button" style="margin-top:12px;" onclick="create3DRecipe()">＋ 新增配方</button>
      </div>
    `;
    return;
  }

  list.innerHTML = rack3DRecipes.map(recipe => {
    const cameraRoi = recipe.roi_config?.camera_roi || {};
    const isDisabled = !recipe.enabled;
    
    return `
      <details class="recipe-card ${isDisabled ? 'disabled' : ''}" id="recipe-3d-${recipe.id}">
        <summary class="recipe-card-summary">
          <span class="recipe-card-name">${escape3DHtml(recipe.recipe_name)}</span>
          <span class="layer-badge">${recipe.layer_count || 3} 层料架配方</span>
          <span class="rack-number-badge">料架号：${escape3DHtml(recipe.rack_type || '未设置')}</span>
          <span class="status-badge ${recipe.enabled ? 'enabled' : 'disabled'}">
            ${recipe.enabled ? '✔ 已启用' : '✕ 已禁用'}
          </span>
          <button class="recipe-rename-button recipe-copy-button" type="button" onclick="event.preventDefault(); event.stopPropagation(); open3DCopyModal(${recipe.id})">增加（复制）</button>
          <button class="recipe-rename-button" type="button" onclick="event.preventDefault(); event.stopPropagation(); open3DRenameModal(${recipe.id})">修改命名</button>
          <button class="recipe-rename-button recipe-delete-button" type="button" onclick="event.preventDefault(); event.stopPropagation(); delete3DRecipe(${recipe.id})">删除</button>
        </summary>
        <div class="recipe-card-body">
          ${render3DWorkbenchData(recipe)}
          <div class="recipe-card-actions">
            <button class="btn btn-sm" onclick="edit3DRecipe(${recipe.id})">编辑</button>
            <button class="btn btn-secondary btn-sm" onclick="toggle3DEnabled(${recipe.id}, ${recipe.enabled})">
              ${recipe.enabled ? '禁用' : '启用'}
            </button>
          </div>
        </div>
      </details>
    `;
  }).join('');
}

// ── 快速修改配方身份信息 ────────────────────────────
window.open3DRenameModal = function(id) {
  const recipe = rack3DRecipes.find(item => Number(item.id) === Number(id));
  if (!recipe) return showToast('配方不存在或尚未加载', 'error');
  document.getElementById('rename-3d-modal-title').textContent = '修改配方信息';
  document.getElementById('rename-3d-save-button').textContent = '保存修改';
  document.getElementById('rename-3d-copy-note').style.display = 'none';
  document.getElementById('rename-3d-source-group').style.display = 'none';
  document.getElementById('rename-3d-name-help').style.display = 'none';
  document.getElementById('rename-3d-source-id').value = '';
  document.getElementById('rename-3d-id').value = recipe.id;
  document.getElementById('rename-3d-name').value = recipe.recipe_name || '';
  document.getElementById('rename-3d-layer-count').value = String(recipe.layer_count || 3);
  document.getElementById('rename-3d-rack-no').value = recipe.rack_type || '';
  document.getElementById('recipe-rename-modal').style.display = 'flex';
  document.getElementById('rename-3d-name').focus();
};

function apply3DCopySource(id) {
  const recipe = rack3DRecipes.find(item => Number(item.id) === Number(id));
  if (!recipe) return false;
  document.getElementById('rename-3d-source-id').value = recipe.id;
  document.getElementById('rename-3d-name').value = `${recipe.recipe_name || '3D配方'} - 副本`;
  document.getElementById('rename-3d-layer-count').value = String(recipe.layer_count || 3);
  document.getElementById('rename-3d-rack-no').value = recipe.rack_type || '';
  return true;
}

window.change3DCopySource = function(id) {
  apply3DCopySource(id);
};

window.open3DCopyModal = function(id = null) {
  if (!rack3DRecipes.length) {
    showToast('暂无可复制的配方，请先新建一份空白配方', 'info');
    create3DRecipe();
    return;
  }
  const selectedId = Number(id) || Number(rack3DRecipes[0].id);
  const sourceSelect = document.getElementById('rename-3d-source-select');
  sourceSelect.innerHTML = rack3DRecipes.map(recipe => `
    <option value="${recipe.id}">${escape3DHtml(recipe.recipe_name)}｜${recipe.layer_count || 3} 层｜${escape3DHtml(recipe.rack_type || '未设置')}</option>
  `).join('');
  sourceSelect.value = String(selectedId);
  document.getElementById('rename-3d-modal-title').textContent = '新增配方（复制已有）';
  document.getElementById('rename-3d-save-button').textContent = '复制并进入 3D 工作台';
  document.getElementById('rename-3d-copy-note').style.display = '';
  document.getElementById('rename-3d-source-group').style.display = '';
  document.getElementById('rename-3d-name-help').style.display = '';
  document.getElementById('rename-3d-id').value = '';
  if (!apply3DCopySource(selectedId)) return showToast('配方不存在或尚未加载', 'error');
  document.getElementById('recipe-rename-modal').style.display = 'flex';
  document.getElementById('rename-3d-name').focus();
};

window.close3DRenameModal = function() {
  document.getElementById('recipe-rename-modal').style.display = 'none';
};

window.save3DRename = async function() {
  const id = Number(document.getElementById('rename-3d-id').value);
  const sourceRecipeId = Number(document.getElementById('rename-3d-source-id').value);
  const recipeName = document.getElementById('rename-3d-name').value.trim();
  const layerCount = Number(document.getElementById('rename-3d-layer-count').value);
  const rackNo = document.getElementById('rename-3d-rack-no').value.trim();
  if ((!id && !sourceRecipeId) || !recipeName) return showToast('请填写配方名称', 'error');
  if (![2, 3].includes(layerCount)) return showToast('请选择 2 层或 3 层料架配方', 'error');
  if (!rackNo) return showToast('请填写料架号', 'error');

  try {
    const isCopy = Boolean(sourceRecipeId);
    const response = await fetch('/vision/api/vision/3d/recipes/', {
      method: isCopy ? 'POST' : 'PATCH',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrf()},
      body: JSON.stringify({
        ...(isCopy ? {source_recipe_id: sourceRecipeId} : {id}),
        recipe_name: recipeName,
        layer_count: layerCount,
        rack_type: rackNo,
      }),
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || '保存失败');
    close3DRenameModal();
    if (isCopy) {
      const createdRecipeId = data.data?.recipe?.id || data.recipe?.id;
      if (!createdRecipeId) throw new Error('副本已创建，但未返回新配方ID');
      window.location.assign(`/vision/rack-locator/?recipe_id=${encodeURIComponent(createdRecipeId)}`);
      return;
    }
    await load3DRecipes();
    showToast('配方信息已更新', 'success');
  } catch (error) {
    showToast('保存失败：' + error.message, 'error');
  }
};

// ── 新增3D配方 ──────────────────────────────────────
window.create3DRecipe = function() {
  document.getElementById('modal-3d-title').textContent = '新增3D配方';
  document.getElementById('modal-3d-id').value = '';
  document.getElementById('modal-3d-name').value = '';
  document.getElementById('modal-3d-layer-count').value = '3';
  document.getElementById('modal-3d-rack-type').value = '';
  document.getElementById('modal-3d-roi-x-min').value = '';
  document.getElementById('modal-3d-roi-x-max').value = '';
  document.getElementById('modal-3d-roi-y-min').value = '';
  document.getElementById('modal-3d-roi-y-max').value = '';
  document.getElementById('modal-3d-roi-z-min').value = '';
  document.getElementById('modal-3d-roi-z-max').value = '';
  document.getElementById('modal-3d-std-x').value = '0';
  document.getElementById('modal-3d-std-y').value = '0';
  document.getElementById('modal-3d-std-z').value = '0';
  document.getElementById('modal-3d-std-rz').value = '0';
  update3DModalWorkbenchData(null);
  document.getElementById('recipe-3d-modal').style.display = 'flex';
  document.getElementById('modal-3d-name').focus();
};

// ── 编辑3D配方 ──────────────────────────────────────
window.edit3DRecipe = async function(id) {
  try {
    const res = await fetch(`/vision/api/vision/3d/recipes/?id=${id}`);
    const data = await res.json();
    if (!data.success) {
      showToast('获取配方失败：' + (data.error || '未知错误'), 'error');
      return;
    }
    
    if (!data.recipes || data.recipes.length === 0) {
      showToast('配方不存在', 'error');
      return;
    }
    
    const recipe = data.recipes[0];
    document.getElementById('modal-3d-title').textContent = '编辑3D配方';
    document.getElementById('modal-3d-id').value = recipe.id;
    document.getElementById('modal-3d-name').value = recipe.recipe_name || '';
    document.getElementById('modal-3d-layer-count').value = String(recipe.layer_count || 3);
    document.getElementById('modal-3d-rack-type').value = recipe.rack_type || '';
    
    // 点云范围使用 camera_roi；四个像素 ROI 由工作台维护，只读展示。
    const roi = recipe.roi_config?.camera_roi || {};
    document.getElementById('modal-3d-roi-x-min').value = roi.x_min ?? '';
    document.getElementById('modal-3d-roi-x-max').value = roi.x_max ?? '';
    document.getElementById('modal-3d-roi-y-min').value = roi.y_min ?? '';
    document.getElementById('modal-3d-roi-y-max').value = roi.y_max ?? '';
    document.getElementById('modal-3d-roi-z-min').value = roi.z_min ?? '';
    document.getElementById('modal-3d-roi-z-max').value = roi.z_max ?? '';
    
    // 标准坐标
    document.getElementById('modal-3d-std-x').value = recipe.standard_x || 0;
    document.getElementById('modal-3d-std-y').value = recipe.standard_y || 0;
    document.getElementById('modal-3d-std-z').value = recipe.standard_z || 0;
    document.getElementById('modal-3d-std-rz').value = recipe.standard_rz || 0;
    update3DModalWorkbenchData(recipe);
    
    document.getElementById('recipe-3d-modal').style.display = 'flex';
  } catch (e) {
    console.error('编辑配方失败:', e);
    showToast('网络请求失败：' + e.message, 'error');
  }
};

// ── 切换3D配方启用状态 ─────────────────────────────
window.toggle3DEnabled = async function(id, currentEnabled) {
  const newEnabled = !currentEnabled;
  try {
    const res = await fetch('/vision/api/vision/3d/recipes/', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify({ id: Number(id), enabled: newEnabled }),
    });
    const data = await res.json();
    if (data.success) {
      showToast(newEnabled ? '配方已启用' : '配方已禁用', 'success');
      await load3DRecipes();
    } else {
      showToast('操作失败：' + (data.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('网络请求失败：' + e.message, 'error');
  }
};

// ── 删除3D配方 ──────────────────────────────────────
window.delete3DRecipe = async function(id) {
  const recipe = rack3DRecipes.find(item => Number(item.id) === Number(id));
  const name = recipe?.recipe_name || `#${id}`;
  if (!confirm(`确定要删除配方「${name}」吗？\n\n此操作不可恢复！`)) return;
  
  try {
    const res = await fetch('/vision/api/vision/3d/recipes/', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify({ id: Number(id) }),
    });
    const data = await res.json();
    if (data.success) {
      showToast('配方已删除', 'success');
      await load3DRecipes();
    } else {
      showToast('删除失败：' + (data.error || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('网络请求失败：' + e.message, 'error');
  }
};

// ── 关闭3D Modal ────────────────────────────────────
window.close3DModal = function() {
  document.getElementById('recipe-3d-modal').style.display = 'none';
};

// ── 提交3D Modal ────────────────────────────────────
window.submit3DModal = async function() {
  const id = document.getElementById('modal-3d-id').value;
  const name = document.getElementById('modal-3d-name').value.trim();
  const layerCount = Number(document.getElementById('modal-3d-layer-count').value);
  const rackNo = document.getElementById('modal-3d-rack-type').value.trim();
  
  // 表单验证
  if (!name) {
    showToast('请填写配方名称', 'error');
    document.getElementById('modal-3d-name').focus();
    return;
  }
  if (![2, 3].includes(layerCount)) {
    showToast('请选择 2 层或 3 层料架配方', 'error');
    document.getElementById('modal-3d-layer-count').focus();
    return;
  }
  if (!rackNo) {
    showToast('请填写料架号', 'error');
    document.getElementById('modal-3d-rack-type').focus();
    return;
  }

  const numberOrNull = (elementId) => {
    const value = document.getElementById(elementId).value;
    if (value === '') return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const existingRecipe = id
    ? rack3DRecipes.find(recipe => String(recipe.id) === String(id))
    : null;
  const existingRoiConfig = existingRecipe?.roi_config || {};

  const payload = {
    recipe_name: name,
    layer_count: layerCount,
    rack_type: rackNo,
    standard_x: Number(document.getElementById('modal-3d-std-x').value) || 0,
    standard_y: Number(document.getElementById('modal-3d-std-y').value) || 0,
    standard_z: Number(document.getElementById('modal-3d-std-z').value) || 0,
    standard_rz: Number(document.getElementById('modal-3d-std-rz').value) || 0,
    // 保留工作台维护的点云模板配置，仅更新 camera_roi。
    roi_config: {
      ...existingRoiConfig,
      camera_roi: {
        x_min: numberOrNull('modal-3d-roi-x-min'),
        x_max: numberOrNull('modal-3d-roi-x-max'),
        y_min: numberOrNull('modal-3d-roi-y-min'),
        y_max: numberOrNull('modal-3d-roi-y-max'),
        z_min: numberOrNull('modal-3d-roi-z-min'),
        z_max: numberOrNull('modal-3d-roi-z-max'),
      },
    },
    enabled: true,
  };

  if (id) {
    payload.id = Number(id);
  }

  try {
    const res = await fetch('/vision/api/vision/3d/recipes/', {
      method: id ? 'PATCH' : 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify(payload),
    });
    
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    
    const data = await res.json();
    
    if (data.success) {
      showToast(id ? '配方已更新' : '配方已创建', 'success');
      close3DModal();
      await load3DRecipes();
    } else {
      showToast('保存失败：' + (data.error || '未知错误'), 'error');
    }
  } catch (e) {
    console.error('保存配方失败:', e);
    showToast('网络请求失败：' + e.message, 'error');
  }
};

// ── ESC键关闭所有Modal ──────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    close3DModal();
    close3DRenameModal();
    closeRackMasterModal();
    closeEditModal();
  }
});

// ── 3D Modal 点击背景关闭 ───────────────────────────
document.getElementById('recipe-3d-modal')?.addEventListener('click', function(e) {
  if (e.target === this) close3DModal();
});

document.getElementById('recipe-rename-modal')?.addEventListener('click', function(e) {
  if (e.target === this) close3DRenameModal();
});

document.getElementById('rack-master-modal')?.addEventListener('click', function(e) {
  if (e.target === this) closeRackMasterModal();
});

// ── 编辑Modal 点击背景关闭 ──────────────────────────
document.getElementById('recipe-edit-modal')?.addEventListener('click', function(e) {
  if (e.target === this) closeEditModal();
});

// ── 初始化 ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (!document.querySelector('[name=csrfmiddlewaretoken]')) {
    const inp = document.createElement('input');
    inp.type = 'hidden';
    inp.name = 'csrfmiddlewaretoken';
    inp.value = '';
    document.body.appendChild(inp);
  }

  document.getElementById('btn-create-recipe')?.addEventListener('click', openCreateModal);
  document.getElementById('modal-pos')?.addEventListener('input', updateModalPositionPreview);

  loadRecipes();
  const requestedTab = new URLSearchParams(window.location.search).get('tab');
  if (requestedTab === 'rack3d' || requestedTab === 'empty2d') {
    document.querySelector(`.recipe-tab[data-recipe-tab="${requestedTab}"]`)?.click();
  } else {
    updateWorkbenchButtons('foam2d');
  }
});


window.emptyRackRecipeSummaryConfig = {
  detailUrl: API.emptyRackRecipe,
  renameUrlTemplate: '/vision/api/recipes/empty-rack-2d/0/rename/'.replace('/0/', '/__RECIPE_ID__/'),
  workbenchUrl: '/vision/foam-inspector/?mode=empty_rack',
};


