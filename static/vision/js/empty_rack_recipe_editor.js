(function () {
  'use strict';

  const config = window.emptyRackRecipeConfig || {};
  const state = {
    loaded: false,
    loading: false,
    recipe: null,
    image: null,
    imageFile: null,
    captureToken: '',
    imageWidth: 0,
    imageHeight: 0,
    rois: [],
    selectedId: null,
    drawing: null,
  };

  const byId = id => document.getElementById(id);
  const canvas = byId('empty-rack-canvas');
  if (!canvas) return;
  const context = canvas.getContext('2d');

  function setMessage(message, type = '') {
    const target = byId('empty-rack-message');
    target.textContent = message;
    target.className = `empty-rack-message ${type}`.trim();
  }

  function setSaveState(text, saved) {
    const target = byId('empty-rack-save-state');
    target.textContent = text;
    target.classList.toggle('saved', Boolean(saved));
  }

  function markDirty() {
    setSaveState('有未保存修改', false);
  }

  function safeNumber(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function drawScene() {
    if (!state.image) return;
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(state.image, 0, 0, canvas.width, canvas.height);
    const lineWidth = Math.max(2, Math.round(canvas.width / 700));
    const fontSize = Math.max(13, Math.round(canvas.width / 65));

    state.rois.forEach((roi, index) => {
      const selected = roi.id === state.selectedId;
      context.save();
      context.lineWidth = selected ? lineWidth * 1.7 : lineWidth;
      context.strokeStyle = selected ? '#fbbf24' : '#22d3ee';
      context.fillStyle = selected ? 'rgba(251,191,36,.17)' : 'rgba(34,211,238,.12)';
      context.fillRect(roi.x, roi.y, roi.width, roi.height);
      context.strokeRect(roi.x, roi.y, roi.width, roi.height);
      const label = `${index + 1} · ${roi.name}`;
      context.font = `700 ${fontSize}px sans-serif`;
      const labelWidth = context.measureText(label).width + 14;
      const labelHeight = fontSize + 10;
      const labelY = Math.max(0, roi.y - labelHeight);
      context.fillStyle = selected ? '#f59e0b' : '#0891b2';
      context.fillRect(roi.x, labelY, labelWidth, labelHeight);
      context.fillStyle = '#fff';
      context.fillText(label, roi.x + 7, labelY + fontSize + 2);
      context.restore();
    });

    if (state.drawing) {
      const roi = normalizedRect(state.drawing.start, state.drawing.current);
      context.save();
      context.setLineDash([10, 7]);
      context.lineWidth = lineWidth;
      context.strokeStyle = '#f8fafc';
      context.fillStyle = 'rgba(255,255,255,.1)';
      context.fillRect(roi.x, roi.y, roi.width, roi.height);
      context.strokeRect(roi.x, roi.y, roi.width, roi.height);
      context.restore();
    }
  }

  function normalizedRect(start, end) {
    const x = Math.max(0, Math.min(start.x, end.x));
    const y = Math.max(0, Math.min(start.y, end.y));
    return {
      x: Math.round(x),
      y: Math.round(y),
      width: Math.round(Math.min(canvas.width, Math.max(start.x, end.x)) - x),
      height: Math.round(Math.min(canvas.height, Math.max(start.y, end.y)) - y),
    };
  }

  function canvasPoint(event) {
    const bounds = canvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(canvas.width, (event.clientX - bounds.left) * canvas.width / bounds.width)),
      y: Math.max(0, Math.min(canvas.height, (event.clientY - bounds.top) * canvas.height / bounds.height)),
    };
  }

  function selectAt(point) {
    const match = [...state.rois].reverse().find(roi => (
      point.x >= roi.x && point.x <= roi.x + roi.width &&
      point.y >= roi.y && point.y <= roi.y + roi.height
    ));
    state.selectedId = match?.id || null;
    renderRoiList();
    drawScene();
  }

  function renderRoiList() {
    const list = byId('empty-rack-roi-list');
    byId('empty-rack-roi-count').textContent = `${state.rois.length} 个 ROI`;
    if (!state.rois.length) {
      list.innerHTML = '<div class="empty-rack-roi-empty">尚未绘制检测区域</div>';
      return;
    }
    list.innerHTML = state.rois.map((roi, index) => `
      <div class="empty-rack-roi-item ${roi.id === state.selectedId ? 'selected' : ''}" data-roi-id="${escapeHtml(roi.id)}">
        <div class="empty-rack-roi-main">
          <span class="empty-rack-roi-index">${index + 1}</span>
          <input class="empty-rack-roi-name" type="text" maxlength="64" value="${escapeHtml(roi.name)}" aria-label="ROI 名称">
          <button class="empty-rack-roi-delete" type="button" title="删除 ROI" aria-label="删除 ROI">×</button>
        </div>
        <div class="empty-rack-roi-coords">x=${roi.x}, y=${roi.y}, w=${roi.width}, h=${roi.height}</div>
      </div>`).join('');

    list.querySelectorAll('.empty-rack-roi-item').forEach(item => {
      const roiId = item.dataset.roiId;
      item.addEventListener('click', () => {
        state.selectedId = roiId;
        renderRoiList();
        drawScene();
      });
      item.querySelector('.empty-rack-roi-name').addEventListener('input', event => {
        const roi = state.rois.find(candidate => candidate.id === roiId);
        if (roi) roi.name = event.target.value;
        state.selectedId = roiId;
        markDirty();
        drawScene();
      });
      item.querySelector('.empty-rack-roi-name').addEventListener('click', event => event.stopPropagation());
      item.querySelector('.empty-rack-roi-delete').addEventListener('click', event => {
        event.stopPropagation();
        state.rois = state.rois.filter(candidate => candidate.id !== roiId);
        if (state.selectedId === roiId) state.selectedId = state.rois[0]?.id || null;
        markDirty();
        renderRoiList();
        drawScene();
      });
    });
  }

  function showImage(image, sourceLabel, coordinateWidth, coordinateHeight) {
    state.image = image;
    const requestedWidth = safeNumber(coordinateWidth, 0);
    const requestedHeight = safeNumber(coordinateHeight, 0);
    state.imageWidth = requestedWidth > 0 ? requestedWidth : (image.naturalWidth || image.width);
    state.imageHeight = requestedHeight > 0 ? requestedHeight : (image.naturalHeight || image.height);
    canvas.width = state.imageWidth;
    canvas.height = state.imageHeight;
    canvas.style.display = 'block';
    byId('empty-rack-canvas-empty').style.display = 'none';
    byId('empty-rack-image-meta').textContent = `${sourceLabel} · ${state.imageWidth} × ${state.imageHeight}px`;
    drawScene();
  }

  function loadImageUrl(url, sourceLabel, coordinateWidth, coordinateHeight) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => {
        showImage(image, sourceLabel, coordinateWidth, coordinateHeight);
        resolve(image);
      };
      image.onerror = () => reject(new Error('基准图加载失败'));
      image.src = url;
    });
  }

  async function loadRecipe() {
    if (state.loading || state.loaded) return;
    state.loading = true;
    setMessage('正在读取空箱检测配方…');
    try {
      const recipeId = new URLSearchParams(window.location.search).get('recipe_id');
      const detailUrl = recipeId
        ? `${config.detailUrl}?id=${encodeURIComponent(recipeId)}`
        : config.detailUrl;
      const response = await fetch(detailUrl);
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '读取配方失败');
      state.recipe = data.recipe || null;
      state.captureToken = '';
      if (!state.recipe) {
        state.loaded = true;
        setMessage('还没有空箱检测配方，请上传基准图并绘制 ROI。');
        return;
      }
      const recipe = state.recipe;
      state.rois = Array.isArray(recipe.roi_config?.regions)
        ? recipe.roi_config.regions.map(roi => ({...roi}))
        : [];
      state.selectedId = state.rois[0]?.id || null;
      byId('empty-rack-name').value = recipe.name || '2D 空箱检测配方';
      byId('empty-rack-difference-threshold').value = safeNumber(recipe.threshold_config?.difference_threshold, .18);
      byId('empty-rack-area-threshold').value = safeNumber(recipe.threshold_config?.min_changed_area_ratio, .06);
      byId('empty-rack-remark').value = recipe.remark || '';
      renderRoiList();
      if (recipe.reference_image_url) {
        await loadImageUrl(`${recipe.reference_image_url}?v=${encodeURIComponent(recipe.updated_at || '')}`, '已保存基准图');
      }
      state.loaded = true;
      setSaveState('已保存', true);
      setMessage(`已加载配方，共 ${state.rois.length} 个检测区域。`, 'success');
    } catch (error) {
      setMessage(error.message, 'error');
    } finally {
      state.loading = false;
    }
  }

  canvas.addEventListener('pointerdown', event => {
    if (!state.image || event.button !== 0) return;
    canvas.setPointerCapture(event.pointerId);
    const point = canvasPoint(event);
    state.drawing = {start: point, current: point};
    drawScene();
  });

  canvas.addEventListener('pointermove', event => {
    if (!state.drawing) return;
    state.drawing.current = canvasPoint(event);
    drawScene();
  });

  canvas.addEventListener('pointerup', event => {
    if (!state.drawing) return;
    const start = state.drawing.start;
    const end = canvasPoint(event);
    const roi = normalizedRect(start, end);
    state.drawing = null;
    if (roi.width < 8 || roi.height < 8) {
      selectAt(end);
      return;
    }
    const id = `roi-${Date.now()}-${state.rois.length + 1}`;
    state.rois.push({
      id,
      name: `检测区 ${state.rois.length + 1}`,
      ...roi,
      enabled: true,
    });
    state.selectedId = id;
    markDirty();
    renderRoiList();
    drawScene();
  });

  byId('empty-rack-upload-btn').addEventListener('click', () => byId('empty-rack-image-input').click());
  byId('empty-rack-image-input').addEventListener('change', async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (state.rois.length && !window.confirm('更换基准图会清空当前 ROI，是否继续？')) {
      event.target.value = '';
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    try {
      state.rois = [];
      state.selectedId = null;
      state.imageFile = file;
      state.captureToken = '';
      await loadImageUrl(objectUrl, file.name);
      renderRoiList();
      markDirty();
      setMessage('基准图已载入，请在图上拖拽绘制检测区域。');
    } catch (error) {
      setMessage(error.message, 'error');
    } finally {
      URL.revokeObjectURL(objectUrl);
    }
  });

  byId('empty-rack-camera-btn')?.addEventListener('click', async () => {
    if (state.rois.length && !window.confirm('重新拍照会清空当前 ROI，是否继续？')) return;
    const button = byId('empty-rack-camera-btn');
    button.disabled = true;
    button.textContent = '正在拍照…';
    setMessage('正在调用料架 2D 相机…');
    try {
      const body = new URLSearchParams({camera_code: config.cameraCode || 'CAM-INSPECT-RACK-01'});
      const response = await fetch(config.cameraPreviewUrl, {
        method: 'POST',
        headers: {
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '',
          'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        },
        body,
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '料架相机拍照失败');
      state.rois = [];
      state.selectedId = null;
      state.imageFile = null;
      state.captureToken = data.capture_token || '';
      await loadImageUrl(
        `${data.image_url}?t=${Date.now()}`,
        '料架相机拍照',
        data.image_width,
        data.image_height,
      );
      renderRoiList();
      markDirty();
      setMessage('拍照完成，请在图上拖拽绘制检测区域。');
    } catch (error) {
      setMessage(error.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = '料架相机拍照';
    }
  });

  byId('empty-rack-clear-btn').addEventListener('click', () => {
    if (!state.rois.length || !window.confirm('确认清空当前全部 ROI？')) return;
    state.rois = [];
    state.selectedId = null;
    markDirty();
    renderRoiList();
    drawScene();
  });

  ['empty-rack-name', 'empty-rack-difference-threshold', 'empty-rack-area-threshold', 'empty-rack-remark']
    .forEach(id => byId(id).addEventListener('input', markDirty));

  byId('empty-rack-save-btn').addEventListener('click', async () => {
    if (!state.image) return setMessage('请先上传空料架基准图。', 'error');
    if (!state.rois.length) return setMessage('请至少绘制一个检测 ROI。', 'error');
    const button = byId('empty-rack-save-btn');
    const form = new FormData();
    if (state.recipe?.id) form.append('id', state.recipe.id);
    if (state.imageFile) form.append('reference_image', state.imageFile, state.imageFile.name);
    if (state.captureToken) form.append('preview_capture_token', state.captureToken);
    form.append('name', byId('empty-rack-name').value.trim() || '2D 空箱检测配方');
    form.append('image_width', state.imageWidth);
    form.append('image_height', state.imageHeight);
    form.append('regions', JSON.stringify(state.rois));
    form.append('difference_threshold', byId('empty-rack-difference-threshold').value);
    form.append('min_changed_area_ratio', byId('empty-rack-area-threshold').value);
    form.append('remark', byId('empty-rack-remark').value.trim());
    button.disabled = true;
    button.textContent = '正在保存…';
    try {
      const response = await fetch(config.saveUrl, {
        method: 'POST',
        headers: {'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''},
        body: form,
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '保存失败');
      state.recipe = data.recipe;
      state.rois = data.recipe.roi_config.regions.map(roi => ({...roi}));
      state.imageFile = null;
      state.captureToken = '';
      setSaveState('已保存', true);
      setMessage(`保存成功：${state.rois.length} 个 ROI 已写入配方。`, 'success');
      renderRoiList();
      if (typeof window.showToast === 'function') window.showToast('空箱检测配方保存成功', 'success');
    } catch (error) {
      setMessage(error.message, 'error');
      if (typeof window.showToast === 'function') window.showToast(error.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = '保存空箱检测配方';
    }
  });

  document.querySelector('[data-recipe-tab="empty2d"]')?.addEventListener('click', loadRecipe);
  window.EmptyRackRecipeEditor = {load: loadRecipe};

  const requestedTab = new URLSearchParams(window.location.search).get('tab');
  if (requestedTab === 'empty2d') {
    document.querySelector('[data-recipe-tab="empty2d"]')?.click();
  } else if (config.autoLoad) {
    loadRecipe();
  }
})();
