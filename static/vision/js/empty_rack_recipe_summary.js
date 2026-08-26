(function () {
  'use strict';
  const config = window.emptyRackRecipeSummaryConfig || {};
  const target = document.getElementById('empty-rack-recipe-summary');
  if (!target) return;
  let currentRecipe = null;

  function escapeHtml(value) {
    return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
  }

  function renderSummary(recipe) {
    currentRecipe = recipe;
    const workbench = document.getElementById('empty-rack-workbench-link');
    if (!recipe) {
      target.innerHTML = '<div class="empty-summary-empty">尚未建立空箱检测配方。进入 2D 工作台载入示教图并绘制 ROI 后保存。</div>';
      if (workbench) workbench.textContent = '新建并进入 2D 工作台';
      return;
    }
    const regions = Array.isArray(recipe.roi_config?.regions) ? recipe.roi_config.regions : [];
    if (workbench) {
      workbench.href = `${config.workbenchUrl}&recipe_id=${encodeURIComponent(recipe.id)}`;
      workbench.textContent = '进入 2D 空箱工作台';
    }
    target.innerHTML = `
      <div class="empty-summary-content">
        <div class="empty-summary-image">${recipe.teaching_image_url
          ? `<img src="${escapeHtml(recipe.teaching_image_url)}?v=${encodeURIComponent(recipe.updated_at || '')}" alt="ROI 示教图">`
          : '<div class="empty-summary-image-placeholder">尚未保存示教图</div>'}</div>
        <div class="empty-summary-body">
          <div class="empty-summary-title">
            <h3>${escapeHtml(recipe.name)}</h3>
            <div class="empty-summary-title-actions"><span>已启用</span><button class="empty-summary-rename-button" type="button" data-empty-rack-rename>修改名称</button></div>
          </div>
          <div class="empty-summary-grid">
            <div><small>ROI 数量</small><strong>${regions.length} 个</strong></div>
            <div><small>示教图分辨率</small><strong>${recipe.image_width} × ${recipe.image_height}</strong></div>
            <div><small>泡棉亮度阈值</small><strong>${recipe.threshold_config?.foam_brightness_threshold ?? 0.55}</strong></div>
            <div><small>最小泡棉面积</small><strong>${recipe.threshold_config?.min_foam_area_ratio ?? 0.03}</strong></div>
          </div>
          <div class="empty-summary-foot">更新时间：${escapeHtml(recipe.updated_at || '—')} · ${escapeHtml(recipe.remark || '无备注')}</div>
        </div>
      </div>`;
  }

  function openRenameEditor() {
    if (!currentRecipe) return;
    const title = target.querySelector('.empty-summary-title');
    if (!title) return;
    title.innerHTML = `
      <div class="empty-summary-name-editor">
        <input type="text" maxlength="100" value="${escapeHtml(currentRecipe.name)}" aria-label="空箱检测配方名称">
        <button class="empty-summary-name-save" type="button" data-empty-rack-name-save>保存名称</button>
        <button type="button" data-empty-rack-name-cancel>取消</button>
        <div class="empty-summary-rename-error" role="alert"></div>
      </div>`;
    const input = title.querySelector('input');
    input.focus();
    input.select();
  }

  async function saveName() {
    const editor = target.querySelector('.empty-summary-name-editor');
    const input = editor?.querySelector('input');
    const errorTarget = editor?.querySelector('.empty-summary-rename-error');
    const name = input?.value.trim() || '';
    if (!name) {
      if (errorTarget) errorTarget.textContent = '请输入配方名称';
      input?.focus();
      return;
    }
    const buttons = editor.querySelectorAll('button');
    buttons.forEach(button => { button.disabled = true; });
    try {
      const url = config.renameUrlTemplate.replace('__RECIPE_ID__', encodeURIComponent(currentRecipe.id));
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '',
        },
        body: JSON.stringify({name}),
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '保存失败');
      renderSummary(data.recipe);
      if (typeof window.showToast === 'function') window.showToast('空箱检测配方名称已更新', 'success');
    } catch (error) {
      buttons.forEach(button => { button.disabled = false; });
      if (errorTarget) errorTarget.textContent = error.message;
    }
  }

  async function loadSummary() {
    try {
      const response = await fetch(config.detailUrl);
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '读取失败');
      renderSummary(data.recipe);
    } catch (error) {
      target.innerHTML = `<div class="empty-summary-empty">空箱配方读取失败：${escapeHtml(error.message)}</div>`;
    }
  }

  target.addEventListener('click', event => {
    if (event.target.closest('[data-empty-rack-rename]')) openRenameEditor();
    if (event.target.closest('[data-empty-rack-name-save]')) saveName();
    if (event.target.closest('[data-empty-rack-name-cancel]')) renderSummary(currentRecipe);
  });
  target.addEventListener('keydown', event => {
    if (!event.target.matches('.empty-summary-name-editor input')) return;
    if (event.key === 'Enter') saveName();
    if (event.key === 'Escape') renderSummary(currentRecipe);
  });

  document.querySelector('[data-recipe-tab="empty2d"]')?.addEventListener('click', loadSummary, {once:true});
})();
