(function () {
  'use strict';
  const config = window.emptyRackRecipeSummaryConfig || {};
  const target = document.getElementById('empty-rack-recipe-summary');
  if (!target) return;

  function escapeHtml(value) {
    return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
  }

  async function loadSummary() {
    try {
      const response = await fetch(config.detailUrl);
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '读取失败');
      const recipe = data.recipe;
      const workbench = document.getElementById('empty-rack-workbench-link');
      if (!recipe) {
        target.innerHTML = '<div class="empty-summary-empty">尚未建立空箱检测配方。进入 2D 工作台载入示教图并绘制 ROI 后保存。</div>';
        if (workbench) workbench.textContent = '新建并进入 2D 工作台';
        return;
      }
      const regions = Array.isArray(recipe.roi_config?.regions) ? recipe.roi_config.regions : [];
      const workbenchUrl = `${config.workbenchUrl}&recipe_id=${encodeURIComponent(recipe.id)}`;
      if (workbench) workbench.href = workbenchUrl;
      target.innerHTML = `
        <div class="empty-summary-content">
          <div class="empty-summary-image">${recipe.teaching_image_url
            ? `<img src="${escapeHtml(recipe.teaching_image_url)}?v=${encodeURIComponent(recipe.updated_at || '')}" alt="ROI 示教图">`
            : '<div class="empty-summary-image-placeholder">尚未保存示教图</div>'}</div>
          <div class="empty-summary-body">
            <div class="empty-summary-title"><h3>${escapeHtml(recipe.name)}</h3><span>已启用</span></div>
            <div class="empty-summary-grid">
              <div><small>ROI 数量</small><strong>${regions.length} 个</strong></div>
              <div><small>示教图分辨率</small><strong>${recipe.image_width} × ${recipe.image_height}</strong></div>
              <div><small>泡棉亮度阈值</small><strong>${recipe.threshold_config?.foam_brightness_threshold ?? 0.55}</strong></div>
              <div><small>最小泡棉面积</small><strong>${recipe.threshold_config?.min_foam_area_ratio ?? 0.03}</strong></div>
            </div>
            <div class="empty-summary-foot">更新时间：${escapeHtml(recipe.updated_at || '—')} · ${escapeHtml(recipe.remark || '无备注')}</div>
          </div>
        </div>`;
    } catch (error) {
      target.innerHTML = `<div class="empty-summary-empty">空箱配方读取失败：${escapeHtml(error.message)}</div>`;
    }
  }

  document.querySelector('[data-recipe-tab="empty2d"]')?.addEventListener('click', loadSummary, {once:true});
})();
