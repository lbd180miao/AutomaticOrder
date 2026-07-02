(function () {
  function el(id) {
    return document.getElementById(id);
  }

  function csrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
  }

  function numberValue(id, fallback) {
    const value = el(id)?.value;
    if (value === undefined || value === null || value === '') return fallback;
    return Number(value);
  }

  function setValue(id, value) {
    const target = el(id);
    if (target) target.value = value ?? '';
  }

  function readRoi3DConfig() {
    return {
      x_min: numberValue('roi-x-min', 0),
      x_max: numberValue('roi-x-max', 0),
      y_min: numberValue('roi-y-min', 0),
      y_max: numberValue('roi-y-max', 0),
      z_min: numberValue('roi-z-min', 0),
      z_max: numberValue('roi-z-max', 0),
      coordinate_system: 'robot',  // 机器人基坐标系
    };
  }

  function currentRecipeData() {
    return {
      standard_x: numberValue('standard-x', 0),
      standard_y: numberValue('standard-y', 0),
      standard_z: numberValue('standard-z', 0),
      standard_rz: numberValue('standard-rz', 0),
      layer_no: numberValue('layer-no', 1),
      roi_3d: readRoi3DConfig(),
    };
  }

  function init() {
    el('btn-capture-standard')?.addEventListener('click', async () => {
      const image = el('rack-location-depth-image');
      el('rack-location-ui-status').textContent = '采集标准图中...';
      const response = await fetch(window.rackLocationRecipeConfig.captureUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify({ recipe_id: window.rackLocationRecipeConfig.recipeId }),
      });
      const data = await response.json();
      if (!data.success) {
        el('rack-location-ui-status').textContent = data.error || '采集失败';
        return;
      }
      image.src = data.preview_image_url;
      image.dataset.naturalWidth = data.image_width;
      image.dataset.naturalHeight = data.image_height;
      el('rack-location-ui-status').textContent = '标准图已采集。';
    });

    el('btn-preview-calculate')?.addEventListener('click', async () => {
      const roi3d = readRoi3DConfig();
      if (roi3d.x_min === 0 && roi3d.x_max === 0 && roi3d.y_min === 0 && roi3d.y_max === 0) {
        el('rack-location-ui-status').textContent = '请先输入 ROI 3D坐标。';
        return;
      }
      el('rack-location-ui-status').textContent = '预计算中...';
      const response = await fetch(window.rackLocationRecipeConfig.previewUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify({
          recipe_id: window.rackLocationRecipeConfig.recipeId,
          recipe_data: currentRecipeData(),
          roi_3d: roi3d,
        }),
      });
      const data = await response.json();
      if (!data.success) {
        el('rack-location-ui-status').textContent = data.error || '预计算失败';
        return;
      }
      const result = data.result || {};
      renderPreviewResult(result);
      el('rack-location-ui-status').textContent = result.success ? '预计算完成。' : ('预计算完成：' + (result.message || ''));
    });

    function renderPreviewResult(result) {
      setValue('actual-x', Number(result.actual_x || 0).toFixed(3));
      setValue('actual-y', Number(result.actual_y || 0).toFixed(3));
      setValue('actual-z', Number(result.actual_z || 0).toFixed(3));
      setValue('offset-x', Number(result.offset_x || 0).toFixed(3));
      setValue('offset-y', Number(result.offset_y || 0).toFixed(3));
      setValue('offset-z', Number(result.offset_z || 0).toFixed(3));
      const confidence = Number(result.confidence || 0);
      setValue('preview-confidence', confidence.toFixed(4));
      setValue('result-message', result.message || result.error_message || '');

      const badge = el('locate-badge');
      if (badge) {
        badge.className = 'badge ' + (result.success ? 'badge-ok' : 'badge-muted');
        badge.textContent = result.success ? '定位完成' : '定位结果';
      }
      const confChip = el('rl-confidence-chip');
      if (confChip) confChip.textContent = `置信度 ${(confidence * 100).toFixed(1)}%`;
      const meta = result.result_data || {};
      const pointsChip = el('rl-points-chip');
      if (pointsChip) pointsChip.textContent = `有效点 ${meta.valid_point_count ?? '—'}`;
      const sourceChip = el('rl-source-chip');
      if (sourceChip) sourceChip.textContent = `数据源 ${meta.source || result.source || '—'}`;
    }

    el('btn-save-standard')?.addEventListener('click', () => {
      if (!el('actual-x')?.value) {
        el('rack-location-ui-status').textContent = '请先预计算，再保存为标准位置。';
        return;
      }
      setValue('standard-x', el('actual-x').value);
      setValue('standard-y', el('actual-y').value);
      setValue('standard-z', el('actual-z').value);
      el('rack-location-ui-status').textContent = '已将预计算实际坐标写入标准坐标，请保存配方。';
    });
  }

  document.addEventListener('DOMContentLoaded', init);
}());
