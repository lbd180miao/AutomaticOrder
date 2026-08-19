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
        target.innerHTML = '<div class="empty-summary-empty">尚未建立空箱检测配方。进入 2D 工作台上传空料架基准图并绘制 ROI 后保存。</div>';
        if (workbench) workbench.textContent = '新建并进入 2D 工作台';
        return;
      }
      const regions = Array.isArray(recipe.roi_config?.regions) ? recipe.roi_config.regions : [];
      const workbenchUrl = `${config.workbenchUrl}&recipe_id=${encodeURIComponent(recipe.id)}`;
      if (workbench) workbench.href = workbenchUrl;
      target.innerHTML = `
        <div class="empty-summary-content">
          <div class="empty-summary-image">${recipe.reference_image_url
            ? `<img src="${escapeHtml(recipe.reference_image_url)}?v=${encodeURIComponent(recipe.updated_at || '')}" alt="空料架基准图">`
            : '<div class="empty-summary-image-placeholder">尚未保存基准图</div>'}</div>
          <div class="empty-summary-body">
            <div class="empty-summary-title"><h3>${escapeHtml(recipe.name)}</h3><span>已启用</span></div>
            <div class="empty-summary-grid">
              <div><small>ROI 数量</small><strong>${regions.length} 个</strong></div>
              <div><small>基准图分辨率</small><strong>${recipe.image_width} × ${recipe.image_height}</strong></div>
              <div><small>像素差异阈值</small><strong>${recipe.threshold_config?.difference_threshold ?? 0.18}</strong></div>
              <div><small>变化面积比例</small><strong>${recipe.threshold_config?.min_changed_area_ratio ?? 0.06}</strong></div>
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
