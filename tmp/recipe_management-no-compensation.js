

// ============================================================
//  视觉配方管理 · 前端逻辑 v1.2 (无Loading版本)
// ============================================================
console.log('配方管理页面已加载 - 整架共用配方库');

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
let modalMode = 'create';
let editingRecipeId = null;
let foamCopySources = [];

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

async function loadRecipes() {
  try {
    const data = await foamApi(API.recipes + '?recipe_type=FOAM_2D');
    foam2DRecipes = data.recipes || [];
    foamCopySources = foam2DRecipes;
    await loadPlcDefault('foam', foam2DRecipes);
    const editId = Number(new URLSearchParams(window.location.search).get('edit'));
    if (editId && !window.foamInitialEditOpened) {
      window.foamInitialEditOpened = true;
      openEditModal(editId);
    }
    renderRecipeCards();
  } catch (error) {
    document.getElementById('foam-recipe-list').textContent = '加载失败：' + error.message;
  }
}

async function loadPlcDefault(kind, recipes) {
  const select = document.getElementById(`plc-default-${kind}`);
  const status = document.getElementById(`plc-default-${kind}-status`);
  try {
    const response = await fetch('/vision/api/recipes/plc-defaults/');
    if (!response.ok) throw new Error('读取默认配方失败');
    const data = await response.json();
    const selected = data[`${kind}_recipe_id`];
    select.replaceChildren(new Option('请选择默认配方', ''));
    select.options[0].disabled = true;
    recipes.forEach(recipe => {
      const enabled = kind === 'foam' ? recipe.is_active : recipe.enabled;
      const name = kind === 'foam' ? recipe.name : recipe.recipe_name;
      const option = new Option(`${name}${enabled ? '' : '（已停用）'}`, recipe.id);
      option.disabled = !enabled;
      select.add(option);
    });
    select.value = selected || '';
    const recipe = recipes.find(item => item.id === selected);
    const enabled = recipe && (kind === 'foam' ? recipe.is_active : recipe.enabled);
    status.textContent = enabled ? 'PLC 下次调用使用此配方，选择后自动保存' : '未设置可用默认配方，PLC 自动视觉将报错';
  } catch (error) {
    status.textContent = error.message;
  }
}

async function savePlcDefault(kind, recipeId) {
  if (!recipeId) return;
  const select = document.getElementById(`plc-default-${kind}`);
  select.disabled = true;
  try {
    const response = await fetch('/vision/api/recipes/plc-defaults/', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrf()},
      body: JSON.stringify({kind, recipe_id: Number(recipeId)}),
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || '默认配方保存失败');
    showToast('默认配方已保存，PLC 下次调用生效', 'success');
  } catch (error) {
    showToast(error.message, 'error');
  } finally {
    await loadPlcDefault(kind, kind === 'foam' ? foam2DRecipes : rack3DRecipes);
    select.disabled = false;
  }
}

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

function foamTemplateSummaryHtml(recipe) {
  const status = recipe.standard_roi_status || recipe.standard_template_status || {};
  if (!status.ready) {
    return `<div class="foam-template-summary missing">${escape2DHtml(status.reason || '请在工作台绘制并保存左右标准 ROI')}</div>`;
  }
  const search = isRoiConfigured(recipe.roi_config?.layerSearchROI) ? '本层搜索区已配置' : '本层搜索区待配置';
  return `<div class="foam-template-summary ready">左右标准 ROI 已配置 · ${search}</div>`;
}

// ── 渲染配方卡片 ───────────────────────────────────
function renderRecipeCards() {
  const query = document.getElementById('foam-recipe-search').value.trim().toLowerCase();
  const recipes = foam2DRecipes.filter(r => `${r.id} ${r.name} ${r.remark || ''} ${r.foam_summary?.material_label || ''} ${r.foam_summary?.segmentation_label || ''} ${r.foam_summary?.configured_mode || ''}`.toLowerCase().includes(query));
  const expanded = new Set([...document.querySelectorAll('#foam-recipe-list details[open]')].map(item => item.id));
  document.getElementById('foam-recipe-list').innerHTML = recipes.length ? recipes.map(recipe => {
    const value = (label, content) => `<div class="rack3d-roi-item"><strong>${label}：</strong><span>${escape2DHtml(content)}</span></div>`;
    return `<details class="recipe-card ${recipe.is_active ? '' : 'disabled'}" id="recipe-2d-${recipe.id}" ${expanded.has(`recipe-2d-${recipe.id}`) ? 'open' : ''}>
      <summary class="recipe-card-summary">
        <span class="recipe-card-name">${escape2DHtml(recipe.name)}</span>
        <span class="rack-number-badge">${escape2DHtml(recipe.foam_summary?.material_label || '未标注颜色')} · ${escape2DHtml(recipe.foam_summary?.segmentation_label || '—')}</span>
        <span class="status-badge ${recipe.is_active ? 'enabled' : 'disabled'}">${recipe.is_active ? '✔ 已启用' : '草稿 / 已停用'}</span>
        <button class="recipe-rename-button recipe-copy-button" type="button" onclick="event.preventDefault(); event.stopPropagation(); copyRecipe(${recipe.id})">增加（复制）</button>
        <button class="recipe-rename-button" type="button" onclick="event.preventDefault(); event.stopPropagation(); openEditModal(${recipe.id})">编辑参数</button>
        <button class="recipe-rename-button" type="button" onclick="event.preventDefault(); event.stopPropagation(); exportRecipeJson('foam2d', ${recipe.id}, this)">导出 JSON</button>
        <button class="recipe-rename-button recipe-delete-button" type="button" onclick="event.preventDefault(); event.stopPropagation(); deleteRecipeById(${recipe.id})">删除</button>
      </summary>
      <div class="recipe-card-body">
        <div class="rack3d-data-block">
          <div class="rack3d-data-title">检测参数</div>
          <div class="rack3d-roi-grid">
            ${foamDecisionSummary(recipe).map(([label, content]) => value(label, content)).join('')}
          </div>
        </div>
        <div class="rack3d-data-block">
          <div class="rack3d-data-title">标准泡棉 ROI</div>
          ${foamTemplateSummaryHtml(recipe)}
        </div>
        <div class="recipe-card-actions">
          <a class="btn btn-sm" href="/vision/foam-inspector/?recipe_id=${recipe.id}">进入 2D 工作台</a>
        </div>
      </div>
    </details>`;
  }).join('') : '<div class="recipe-empty">暂无匹配配方</div>';
}

// ── 选择配方编辑（已弃用，保留兼容）───────────────
window.selectRecipeForEdit = function(recipeId) {
  // 此函数已废弃，直接打开编辑弹窗
  openEditModal(recipeId);
};

const foamIntegrityKeys = [
  'min_area_ratio', 'max_area_ratio', 'max_missing_ratio', 'max_excess_ratio', 'max_local_missing_ratio',
];

function foamEditField(key) {
  return document.getElementById('edit-quality-' + key.replaceAll('_', '-'));
}

function setFoamEditFieldsVisible(id, visible) {
  const group = document.getElementById(id);
  group.hidden = !visible;
  for (const input of group.querySelectorAll('input')) input.disabled = !visible;
}

function refreshFoamEditFields(recipe) {
  const material = foamEditField('material').value;
  const summary = recipe.foam_summary || {};
  const usesThreshold = material === 'white' || (material === 'unspecified' && summary.uses_hsv_thresholds);
  const algorithmLabel = {gray: '阴影分割', white: '阈值分割'}[material] || summary.segmentation_label || '阈值分割';
  foamEditField('segmentation').textContent = '使用' + algorithmLabel;
  setFoamEditFieldsVisible('edit-hsv-fields', usesThreshold);

  const separated = foamEditField('decision_mode').value === 'separated-v2';
  setFoamEditFieldsVisible('edit-coverage-fields', !separated);
  setFoamEditFieldsVisible('edit-optional-integrity', !separated);
  setFoamEditFieldsVisible('edit-integrity-fields', separated || document.getElementById('edit-use-integrity').checked);
  for (const key of foamIntegrityKeys.slice(0, 4)) foamEditField(key).required = separated;
  document.getElementById('edit-decision-hint').textContent = separated
    ? '泡棉形状对齐后检查面积、缺损和超出，位置偏移单独判定。'
    : '按泡棉在标准 ROI 内的覆盖比例和位置偏移判定。';

  const mm = document.getElementById('edit-use-mm').checked
    && foamEditField('pixels_per_mm_x').valueAsNumber > 0
    && foamEditField('pixels_per_mm_y').valueAsNumber > 0;
  setFoamEditFieldsVisible('edit-offset-mm-fields', mm);
  setFoamEditFieldsVisible('edit-offset-px-fields', !mm);
  document.getElementById('edit-offset-hint').textContent = mm
    ? '偏移按毫米判定。标定系数见高级参数。'
    : '偏移按像素判定。可在高级参数设置毫米标定。';

  setFoamEditFieldsVisible('edit-merge-fields', foamEditField('merge_enabled').checked);
}

window.openEditModal = function(recipeId) {
  const recipe = foam2DRecipes.find(r => r.id === recipeId);
  if (!recipe) return;

  const algorithm = recipe.algorithm_config || {};
  const thresholds = recipe.threshold_config || {};
  const alignment = recipe.foam_summary?.alignment || {};
  foamEditField('merge_enabled').checked = algorithm.fragment_merge?.enabled === true;
  foamEditField('merge_gap').value = algorithm.fragment_merge?.max_gap_px ?? 12;
  foamEditField('merge_color').value = algorithm.fragment_merge?.max_color_distance ?? 25;
  foamEditField('material').value = recipe.foam_summary?.material_type || 'unspecified';
  foamEditField('min_v').value = algorithm.segmentation_config?.foam_min_v ?? 140;
  foamEditField('max_s').value = algorithm.segmentation_config?.foam_max_s ?? 80;
  foamEditField('decision_mode').value = thresholds.decision_mode || 'legacy';
  document.getElementById('edit-use-integrity').checked = foamIntegrityKeys.some(key => thresholds[key] != null);
  for (const key of foamIntegrityKeys) {
    foamEditField(key).value = thresholds[key] == null ? '' : Number((thresholds[key] * 100).toPrecision(12));
  }
  document.getElementById('edit-use-mm').checked = (alignment.max_offset_mm ?? 2) > 0;
  foamEditField('pixels_per_mm_x').value = alignment.pixels_per_mm_x ?? 0;
  foamEditField('pixels_per_mm_y').value = alignment.pixels_per_mm_y ?? 0;
  foamEditField('max_offset_x_mm').value = alignment.max_offset_x_mm ?? 2;
  foamEditField('max_offset_y_mm').value = alignment.max_offset_y_mm ?? 2;
  document.getElementById('edit-offset-x-px').value = alignment.max_offset_x_px ?? 30;
  document.getElementById('edit-offset-y-px').value = alignment.max_offset_y_px ?? 30;
  document.getElementById('edit-name').value = recipe.name;
  document.getElementById('edit-remark').value = recipe.remark || '';
  document.getElementById('edit-active').checked = recipe.is_active;
  document.getElementById('edit-thresh-cov').value = Number((thresholdValue(thresholds, ['coverage_threshold', 'minCoverage'], 0.75) * 100).toPrecision(12));

  document.getElementById('edit-modal-title').textContent = `编辑配方 · ${recipe.name}`;
  document.getElementById('edit-modal-id').value = recipe.id;
  document.getElementById('edit-advanced-settings').open = false;
  document.getElementById('edit-standard-template-data').innerHTML = foamTemplateSummaryHtml(recipe);
  document.getElementById('edit-standard-template-workbench').href = `/vision/foam-inspector/?recipe_id=${recipe.id}`;

  refreshFoamEditFields(recipe);
  const modal = document.getElementById('recipe-edit-modal');
  modal.oninput = () => refreshFoamEditFields(recipe);
  modal.style.display = 'flex';
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
    if (!input.checkValidity()) {
      const details = input.closest('details');
      if (details) details.open = true;
      input.reportValidity();
      return;
    }
  }
  const name = document.getElementById('edit-name').value.trim();
  if (!name) { showToast('请输入配方名称', 'error'); return; }

  const threshold_config = {decision_mode: foamEditField('decision_mode').value};
  const coverage = document.getElementById('edit-thresh-cov');
  if (!coverage.disabled) {
    threshold_config.coverage_threshold = coverage.valueAsNumber / 100;
    threshold_config.minCoverage = threshold_config.coverage_threshold;
  }
  for (const key of foamIntegrityKeys) {
    const input = foamEditField(key);
    threshold_config[key] = input.disabled || input.value === '' ? null : input.valueAsNumber / 100;
  }

  const alignment = recipe.foam_summary?.alignment || {};
  const useMm = document.getElementById('edit-use-mm').checked;
  if (useMm !== ((alignment.max_offset_mm ?? 2) > 0)) {
    // Keep per-axis millimeter limits when the legacy mode flag changes.
    threshold_config.max_offset_mm = useMm ? 2 : 0;
    threshold_config.max_offset_x_mm = foamEditField('max_offset_x_mm').valueAsNumber;
    threshold_config.max_offset_y_mm = foamEditField('max_offset_y_mm').valueAsNumber;
  }
  for (const axis of ['x', 'y']) {
    const scale = foamEditField('pixels_per_mm_' + axis).valueAsNumber;
    if (scale !== (alignment['pixels_per_mm_' + axis] ?? 0)) {
      threshold_config['pixels_per_mm_' + axis] = scale;
      if (scale === 0) threshold_config['mm_per_pixel_' + axis] = 0;
    }
    const mmInput = foamEditField('max_offset_' + axis + '_mm');
    const pxInput = document.getElementById('edit-offset-' + axis + '-px');
    const offsetInput = mmInput.disabled ? pxInput : mmInput;
    const unit = mmInput.disabled ? 'px' : 'mm';
    threshold_config[`max_offset_${axis}_${unit}`] = offsetInput.valueAsNumber;
  }
  if ('max_offset_x_px' in threshold_config) {
    threshold_config.maxOffsetX = threshold_config.max_offset_x_px;
    threshold_config.maxOffsetY = threshold_config.max_offset_y_px;
    threshold_config.max_offset_px = Math.max(threshold_config.maxOffsetX, threshold_config.maxOffsetY);
  }
  if ('max_offset_x_mm' in threshold_config) {
    threshold_config.maxOffsetXMm = threshold_config.max_offset_x_mm;
    threshold_config.maxOffsetYMm = threshold_config.max_offset_y_mm;
  }

  const algorithm_config = {material_type: foamEditField('material').value};
  if (!foamEditField('min_v').disabled) {
    algorithm_config.segmentation_config = {
      foam_min_v: foamEditField('min_v').valueAsNumber,
      foam_max_s: foamEditField('max_s').valueAsNumber,
    };
  }
  const merge = foamEditField('merge_enabled').checked;
  algorithm_config.fragment_merge = {...recipe.algorithm_config?.fragment_merge, enabled: merge};
  if (merge) {
    algorithm_config.fragment_merge.max_gap_px = foamEditField('merge_gap').valueAsNumber;
    algorithm_config.fragment_merge.max_color_distance = foamEditField('merge_color').valueAsNumber;
  }

  try {
    const res = await fetch(API.saveRecipe, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: recipe.id,
        shared_recipe: true,
        pos: recipe.pos,
        name,
        camera_side: recipe.camera_side,
        image_width: recipe.image_width,
        image_height: recipe.image_height,
        roi_config: recipe.roi_config || {},
        threshold_config,
        algorithm_config,
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

  // 2D配方的新增逻辑
  modalMode = 'create';
  editingRecipeId = null;
  document.getElementById('modal-title').textContent = '新增配方';
  document.getElementById('modal-name').value = '';
  document.getElementById('modal-remark').value = '';
  renderCopySourceOptions();
  document.getElementById('recipe-modal').style.display = 'flex';
};

function renderCopySourceOptions(selectedId = '') {
  const select = document.getElementById('modal-copy-source');
  select.replaceChildren(new Option('不复制，使用默认参数', ''));
  foamCopySources.forEach(source => {
    select.add(new Option(
      source.name,
      String(source.id),
    ));
  });
  select.value = selectedId ? String(selectedId) : '';
}

window.copyRecipe = function(recipeId) {
  const recipe = foam2DRecipes.find(r => r.id === recipeId);
  if (!recipe) return;

  modalMode = 'create';
  editingRecipeId = null;
  document.getElementById('modal-title').textContent = '复制配方';
  document.getElementById('modal-name').value = recipe.name + ' (副本)';
  document.getElementById('modal-remark').value = recipe.remark || '';
  renderCopySourceOptions(recipe.id);
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
  const remark = document.getElementById('modal-remark').value.trim();
  const sourceRecipeId = document.getElementById('modal-copy-source').value;

  if (!name) {
    showToast('请输入配方名称', 'error');
    return;
  }

  try {
    const res = await fetch(API.createRecipe, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        shared_recipe: true,
        pos: 0,
        source_recipe_id: sourceRecipeId || null,
        remark: remark,
      }),
    });
    const data = await res.json();
    if (data.success) {
      showToast('配方创建成功', 'success');
      closeModal();
      await loadRecipes();
      openEditModal(data.recipe.id);
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
    if(createBtn) createBtn.textContent = '新增配方';
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
    return `<div class="rack-mapping-card"><div class="rack-mapping-card-head"><strong>第 ${mapping.layer_no} 层</strong><span class="rack-master-badge ${stateClass}" title="${escape3DHtml(issues)}">${stateText}</span></div><label style="font-size:calc(12px + var(--ui-font-increase, 0px));color:#64748b;">3D 定位配方</label><select id="rack-map-recipe-${positionNo}-${mapping.layer_no}">${rackVisionOptions(mapping, recipe.rack_type)}</select><label style="display:block;margin-top:8px;font-size:calc(12px + var(--ui-font-increase, 0px));color:#64748b;">机器人目标位</label><input id="rack-map-target-${positionNo}-${mapping.layer_no}" value="${escape3DHtml(mapping.robot_target_code || '')}" placeholder="ROBOT_P${positionNo}_L${mapping.layer_no}"><button class="btn btn-secondary btn-sm" onclick="saveRackMapping(${positionNo}, ${mapping.layer_no})">保存第 ${mapping.layer_no} 层</button></div>`;
  }).join('');
  return `${rackSceneHeader(`RECIPE 0${positionNo + 1}`, `${positionNo}号位 · 分层定位配方`, `为${positionNo}号位的每一层选择独立 3D 定位配方和机器人目标位。`, recipe, '<a href="/vision/rack-locator/" class="btn btn-secondary btn-sm">3D 示教工作台</a><button class="btn btn-sm" onclick="create3DRecipe()">新增3D配方</button>')}
    <div class="rack-scene-body"><div class="rack-loop-banner"><div><strong>${positionNo}号位：${readyCount}/${recipe.layer_count} 层已就绪</strong><br><span>配方映射只建立引用，不会修改原有 3D ROI、模板或标定数据。</span></div><span>${escape3DHtml(recipe.rack_type)}</span></div><div class="rack-mapping-cards">${cards || '<div class="rack-master-empty">暂无可配置层，请先设置层数。</div>'}</div>${recipe.layer_count > 3 ? '<div class="rack-scene-note">现有 3D 定位算法仅支持第1～3层；第4层及以上数据会保留，但不能标记为生产就绪。</div>' : ''}</div>`;
}

function renderRackInspectionScene(recipe) {
  return `${rackSceneHeader('RECIPE 04', '检测配方与装箱规则', '集中查看这份料架配方关联的泡棉和装箱规则入口。', recipe)}
    <div class="rack-scene-body"><div class="rack-flow-grid">
      <article class="rack-flow-card" style="padding-left:16px;"><h4>2D 泡棉检测配方</h4><p>本料架共 ${recipe.total_quantity} 个装箱位置；整架共用一套泡棉检测 ROI 和阈值。</p><div class="rack-flow-actions"><a href="/vision/foam-inspector/" class="btn btn-sm">编辑泡棉配方</a><a href="/vision/recipes/?tab=foam2d" class="btn btn-secondary btn-sm">查看泡棉配方</a></div></article>
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
  const rois = roiConfig.cloud_center_config?.rois || [];
  const reference = roiConfig.cloud_center_reference;
  const measurement = reference?.measurement;
  const valid = measurement?.success && measurement.coordinateSystem === 'camera' && measurement.unit === 'mm';
  const labels = [['P1_cross', '模板区域 1'], ['P2_cross', '模板区域 2']].slice(0, roiConfig.cloud_center_config?.rack_layers === 2 ? 1 : 2);
  const templateRows = ['P1', 'P2'].slice(0, labels.length).map((name, index) => {
    const point = valid ? measurement.points?.find(item => item.name === name && item.success) : null;
    const coords = point?.xyz;
    const text = Array.isArray(coords) && coords.length === 3 && coords.every(Number.isFinite)
      ? coords.map(value => format3DNumber(value)).join(' / ') : '—';
    return `<div class="rack3d-template-detail">模板区域 ${index + 1}：${text}</div>`;
  }).join('');
  return `
    <div class="rack3d-data-block">
      <div class="rack3d-data-title">单框模板区域（2D 原图像素）</div>
      <div class="rack3d-roi-grid">${labels.map(([target, label]) => {
        const roi = rois.find(item => item.target === target);
        return `<div class="rack3d-roi-item">${label}：${formatPixelRoi(roi ? {...roi, w: roi.width ?? roi.w, h: roi.height ?? roi.h} : null)}</div>`;
      }).join('')}</div>
    </div>
    <div class="rack3d-data-block">
      <div class="rack3d-data-title">点云标准模板中心（相机原始 X / Y / Z · mm）</div>
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
  loadPlcDefault('rack', rack3DRecipes);
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
          <button class="recipe-rename-button" type="button" onclick="event.preventDefault(); event.stopPropagation(); exportRecipeJson('rack3d', ${recipe.id}, this)">导出 JSON</button>
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

// JSON transfer uses the saved recipe, including template and ROI data.
window.exportRecipeJson = async function(kind, id, button) {
  button.disabled = true;
  try {
    const response = await fetch(`/vision/api/recipes/transfer/${kind}/${id}/export/`);
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || '导出失败');
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = `${kind}-recipe-${id}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    showToast('配方 JSON 已导出', 'success');
  } catch (error) {
    showToast(error.message, 'error');
  } finally {
    button.disabled = false;
  }
};

window.importRecipeJson = async function(input) {
  const file = input.files[0];
  const kind = currentTab;
  input.value = '';
  if (!file) return;
  if (file.size > 32 * 1024 * 1024) {
    showToast('请选择不超过 32 MB 的 JSON 文件', 'error');
    return;
  }
  const button = document.getElementById('btn-import-recipe');
  button.disabled = true;
  try {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`/vision/api/recipes/transfer/${kind}/import/`, {
      method: 'POST', headers: {'X-CSRFToken': getCsrf()}, body: form,
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || '导入失败');
    await (kind === 'foam2d' ? loadRecipes() : load3DRecipes());
    showToast(`已导入「${data.name}」，PLC 默认配方保持不变`, 'success');
    if (data.warnings.length) alert('配方已导入，请检查以下关联：\n' + data.warnings.join('\n'));
  } catch (error) {
    showToast('导入失败：' + error.message, 'error');
  } finally {
    button.disabled = false;
  }
};

// ── 初始化 ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (!document.querySelector('[name=csrfmiddlewaretoken]')) {
    const inp = document.createElement('input');
    inp.type = 'hidden';
    inp.name = 'csrfmiddlewaretoken';
    inp.value = 'test';
    document.body.appendChild(inp);
  }

  document.getElementById('btn-create-recipe')?.addEventListener('click', openCreateModal);


  loadRecipes();
  const requestedTab = new URLSearchParams(window.location.search).get('tab');
  if (requestedTab === 'rack3d') {
    document.querySelector(`.recipe-tab[data-recipe-tab="${requestedTab}"]`)?.click();
  } else {
    updateWorkbenchButtons('foam2d');
  }
});

