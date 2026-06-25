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

  function readRoiConfig() {
    try {
      return JSON.parse(el('roi-config-input')?.value || '{}');
    } catch (_) {
      return {};
    }
  }

  function writeRoiConfig(roi) {
    const config = readRoiConfig();
    config.target_roi = {
      x: roi.x,
      y: roi.y,
      w: roi.w,
      h: roi.h,
      feature_type: el('roi-feature-type')?.value || 'rack_reference',
    };
    el('roi-config-input').value = JSON.stringify(config);
    setValue('roi-x', config.target_roi.x);
    setValue('roi-y', config.target_roi.y);
    setValue('roi-w', config.target_roi.w);
    setValue('roi-h', config.target_roi.h);
    setValue('roi-feature-type', config.target_roi.feature_type);
  }

  function currentRecipeData() {
    return {
      standard_x: numberValue('standard-x', 0),
      standard_y: numberValue('standard-y', 0),
      standard_z: numberValue('standard-z', 0),
      standard_rz: numberValue('standard-rz', 0),
      max_offset_x: numberValue('max-offset-x', 20),
      max_offset_y: numberValue('max-offset-y', 20),
      max_offset_z: numberValue('max-offset-z', 20),
      confidence_threshold: numberValue('confidence-threshold', 0.8),
      layer_no: numberValue('layer-no', 1),
      hand_eye_config: JSON.parse(el('hand-eye-config-input')?.value || '{"matrix":"identity"}'),
    };
  }

  function init() {
    const image = el('rack-location-depth-image');
    const canvas = el('rack-location-canvas');
    if (!image || !canvas) return;
    const context = canvas.getContext('2d');
    const state = { drawing: false, start: null, displayRoi: null };

    function resizeCanvas() {
      const rect = image.getBoundingClientRect();
      canvas.width = Math.max(1, Math.round(rect.width));
      canvas.height = Math.max(1, Math.round(rect.height));
      draw();
    }

    function draw() {
      context.clearRect(0, 0, canvas.width, canvas.height);
      const roi = state.displayRoi;
      if (!roi) return;
      context.save();
      context.strokeStyle = '#22c55e';
      context.lineWidth = 3;
      context.setLineDash([8, 4]);
      context.strokeRect(roi.x, roi.y, roi.w, roi.h);
      context.fillStyle = 'rgba(34, 197, 94, 0.16)';
      context.fillRect(roi.x, roi.y, roi.w, roi.h);
      context.fillStyle = '#22c55e';
      context.font = '14px sans-serif';
      context.fillText('target ROI', roi.x + 8, Math.max(18, roi.y + 18));
      context.restore();
    }

    function pointerToCanvas(event) {
      const rect = canvas.getBoundingClientRect();
      return {
        x: Math.max(0, Math.min(canvas.width, event.clientX - rect.left)),
        y: Math.max(0, Math.min(canvas.height, event.clientY - rect.top)),
      };
    }

    function setReadout(text) {
      const node = el('rl-roi-readout');
      if (node) node.textContent = text;
    }

    function readoutFromReal(realRoi) {
      if (!realRoi) {
        setReadout('拖拽绘制 ROI');
        return;
      }
      setReadout(`ROI  x=${realRoi.x}  y=${realRoi.y}  w=${realRoi.w}  h=${realRoi.h}`);
    }

    function displayToReal(displayRoi) {
      const naturalWidth = image.naturalWidth || Number(image.dataset.naturalWidth) || canvas.width;
      const naturalHeight = image.naturalHeight || Number(image.dataset.naturalHeight) || canvas.height;
      const sx = naturalWidth / canvas.width;
      const sy = naturalHeight / canvas.height;
      return {
        x: Math.round(displayRoi.x * sx),
        y: Math.round(displayRoi.y * sy),
        w: Math.round(displayRoi.w * sx),
        h: Math.round(displayRoi.h * sy),
      };
    }

    function realToDisplay(realRoi) {
      const naturalWidth = image.naturalWidth || Number(image.dataset.naturalWidth) || canvas.width;
      const naturalHeight = image.naturalHeight || Number(image.dataset.naturalHeight) || canvas.height;
      const sx = canvas.width / naturalWidth;
      const sy = canvas.height / naturalHeight;
      return {
        x: Math.round(realRoi.x * sx),
        y: Math.round(realRoi.y * sy),
        w: Math.round(realRoi.w * sx),
        h: Math.round(realRoi.h * sy),
      };
    }

    function loadInitialRoi() {
      const roi = readRoiConfig().target_roi;
      if (!roi) return;
      writeRoiConfig(roi);
      state.displayRoi = realToDisplay(roi);
      draw();
      readoutFromReal(roi);
    }

    canvas.addEventListener('mousedown', (event) => {
      state.drawing = true;
      state.start = pointerToCanvas(event);
      state.displayRoi = { x: state.start.x, y: state.start.y, w: 0, h: 0 };
      draw();
    });

    canvas.addEventListener('mousemove', (event) => {
      if (!state.drawing || !state.start) return;
      const current = pointerToCanvas(event);
      state.displayRoi = {
        x: Math.min(state.start.x, current.x),
        y: Math.min(state.start.y, current.y),
        w: Math.abs(current.x - state.start.x),
        h: Math.abs(current.y - state.start.y),
      };
      draw();
      readoutFromReal(displayToReal(state.displayRoi));
    });

    window.addEventListener('mouseup', () => {
      if (!state.drawing || !state.displayRoi) return;
      state.drawing = false;
      state.start = null;
      if (state.displayRoi.w < 3 || state.displayRoi.h < 3) {
        state.displayRoi = null;
        draw();
        return;
      }
      const realRoi = displayToReal(state.displayRoi);
      writeRoiConfig(realRoi);
      readoutFromReal(realRoi);
      el('rack-location-ui-status').textContent = 'ROI 已更新，可预计算或保存配方。';
    });

    el('btn-redraw-roi')?.addEventListener('click', () => {
      state.displayRoi = null;
      el('roi-config-input').value = '{}';
      ['roi-x', 'roi-y', 'roi-w', 'roi-h'].forEach((id) => setValue(id, ''));
      draw();
      readoutFromReal(null);
      el('rack-location-ui-status').textContent = '请重新在图上拖拽绘制 ROI。';
    });

    el('btn-capture-standard')?.addEventListener('click', async () => {
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
      el('rack-location-ui-status').textContent = '标准图已采集，可绘制 ROI。';
    });

    el('btn-preview-calculate')?.addEventListener('click', async () => {
      const roiConfig = readRoiConfig();
      if (!roiConfig.target_roi) {
        el('rack-location-ui-status').textContent = '请先绘制 ROI。';
        return;
      }
      el('rack-location-ui-status').textContent = '预计算中...';
      const response = await fetch(window.rackLocationRecipeConfig.previewUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify({
          recipe_id: window.rackLocationRecipeConfig.recipeId,
          roi_config: roiConfig,
          recipe_data: currentRecipeData(),
        }),
      });
      const data = await response.json();
      if (!data.success) {
        el('rack-location-ui-status').textContent = data.error || '预计算失败';
        return;
      }
      const result = data.result || {};
      renderPreviewResult(result);
      el('rack-location-ui-status').textContent = result.locate_ok ? '预计算 OK。' : ('预计算 NG：' + (result.error_message || result.error_code || '未知错误'));
    });

    function colorOffset(id, value, limit) {
      const input = el(id);
      if (!input) return;
      input.value = Number(value || 0).toFixed(3);
      input.classList.remove('rl-out', 'rl-in');
      if (Number.isFinite(limit)) {
        input.classList.add(Math.abs(Number(value || 0)) > limit ? 'rl-out' : 'rl-in');
      }
    }

    function renderPreviewResult(result) {
      const recipe = currentRecipeData();
      setValue('actual-x', Number(result.actual_x || 0).toFixed(3));
      setValue('actual-y', Number(result.actual_y || 0).toFixed(3));
      setValue('actual-z', Number(result.actual_z || 0).toFixed(3));
      colorOffset('offset-x', result.offset_x, recipe.max_offset_x);
      colorOffset('offset-y', result.offset_y, recipe.max_offset_y);
      colorOffset('offset-z', result.offset_z, recipe.max_offset_z);
      const confidence = Number(result.confidence || 0);
      setValue('preview-confidence', confidence.toFixed(4));
      setValue('locate-ok', result.locate_ok ? 'OK' : 'NG');
      setValue('error-message', result.error_message || '');

      const badge = el('locate-badge');
      if (badge) {
        badge.className = 'badge ' + (result.locate_ok ? 'badge-ok' : 'badge-fail');
        badge.textContent = result.locate_ok ? '定位 OK' : '定位 NG';
      }
      const threshold = recipe.confidence_threshold;
      const confChip = el('rl-confidence-chip');
      if (confChip) confChip.textContent = `置信度 ${(confidence * 100).toFixed(1)}% / 阈值 ${(threshold * 100).toFixed(0)}%`;
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

    image.addEventListener('load', () => {
      resizeCanvas();
      loadInitialRoi();
    });
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();
    loadInitialRoi();
  }

  document.addEventListener('DOMContentLoaded', init);
}());
