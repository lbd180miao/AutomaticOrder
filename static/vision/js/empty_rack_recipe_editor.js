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
    sourceRecord: null,
    imageWidth: 0,
    imageHeight: 0,
    rois: [],
    selectedId: null,
    interaction: null,
    published: false,
    dirty: false,
    trialCompleted: false,
    recipes: [],
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
    state.dirty = true;
    state.trialCompleted = false;
    state.published = false;
    renderTrialResult(null, '参数已修改，可先计算预览，也可直接保存配方。');
    setSaveState('有未保存修改', false);
    updateProgress();
  }

  function renderTrialResult(result, message = '') {
    const target = byId('empty-rack-trial-result');
    if (!target) return;
    if (!result) {
      target.className = 'empty-rack-trial-result idle';
      target.textContent = message || '尚未试跑';
      return;
    }
    const regions = Array.isArray(result.regions) ? result.regions : [];
    target.className = `empty-rack-trial-result ${result.is_empty ? 'pass' : 'fail'}`;
    target.innerHTML = `
      <div class="empty-rack-trial-summary">
        <strong>${result.is_empty ? '空箱 · OK' : '检测到占用 · NG'}</strong>
        <span>${regions.length} 个区域，${Number(result.occupied_count || 0)} 个异常</span>
      </div>
      ${result.result_image_url ? `<img src="${escapeHtml(result.result_image_url)}" alt="空箱试跑标注结果">` : ''}
      <div class="empty-rack-trial-regions">
        ${regions.map((region, index) => `
          <span class="${region.is_empty ? 'ok' : 'ng'}">
            ${escapeHtml(region.name || `检测区 ${index + 1}`)}：${(Number(region.foam_area_ratio || 0) * 100).toFixed(1)}%
          </span>`).join('')}
      </div>`;
  }

  function updateProgress() {
    const nameReady = Boolean(byId('empty-rack-name')?.value.trim());
    const imageReady = Boolean(state.image);
    const roiReady = state.rois.length > 0;
    const brightness = Number(byId('empty-rack-brightness-threshold')?.value);
    const area = Number(byId('empty-rack-foam-area-threshold')?.value);
    const thresholdReady = Number.isFinite(brightness) && brightness >= 0 && brightness <= 1 &&
      Number.isFinite(area) && area >= 0 && area <= 1;
    const completed = [nameReady, imageReady, roiReady, thresholdReady, state.published];
    const firstIncomplete = completed.slice(0, 4).findIndex(value => !value);
    const currentStep = firstIncomplete >= 0 ? firstIncomplete + 1 : (state.published ? 0 : 5);
    document.querySelectorAll('#empty-rack-progress [data-step]').forEach(step => {
      const number = Number(step.dataset.step);
      step.classList.toggle('done', Boolean(completed[number - 1]));
      step.classList.toggle('current', number === currentStep);
    });
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

  function resizeHandles(roi) {
    return {
      nw: {x: roi.x, y: roi.y},
      ne: {x: roi.x + roi.width, y: roi.y},
      se: {x: roi.x + roi.width, y: roi.y + roi.height},
      sw: {x: roi.x, y: roi.y + roi.height},
    };
  }

  function roiAt(point) {
    return [...state.rois].reverse().find(roi => (
      point.x >= roi.x && point.x <= roi.x + roi.width &&
      point.y >= roi.y && point.y <= roi.y + roi.height
    ));
  }

  function handleAt(point, roi) {
    if (!roi) return null;
    const tolerance = Math.max(18, canvas.width / 120);
    return Object.entries(resizeHandles(roi)).find(([, handle]) => (
      Math.abs(point.x - handle.x) <= tolerance && Math.abs(point.y - handle.y) <= tolerance
    ))?.[0] || null;
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
      if (selected) {
        const handleSize = Math.max(18, Math.round(canvas.width / 120));
        Object.values(resizeHandles(roi)).forEach(handle => {
          context.fillStyle = '#fff';
          context.strokeStyle = '#f59e0b';
          context.lineWidth = lineWidth;
          context.fillRect(handle.x - handleSize / 2, handle.y - handleSize / 2, handleSize, handleSize);
          context.strokeRect(handle.x - handleSize / 2, handle.y - handleSize / 2, handleSize, handleSize);
        });
      }
      context.restore();
    });

    if (state.interaction?.type === 'draw') {
      const roi = normalizedRect(state.interaction.start, state.interaction.current);
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
    const match = roiAt(point);
    state.selectedId = match?.id || null;
    renderRoiList();
    drawScene();
  }

  function renderRoiList() {
    const list = byId('empty-rack-roi-list');
    byId('empty-rack-roi-count').textContent = `${state.rois.length} 个 ROI`;
    if (!state.rois.length) {
      list.innerHTML = '<div class="empty-rack-roi-empty">尚未绘制检测区域</div>';
      updateProgress();
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
        ${roi.id === state.selectedId ? `
        <div class="empty-rack-roi-adjust" aria-label="ROI 坐标微调">
          <label>X<input type="number" data-roi-field="x" min="0" max="${Math.max(0, state.imageWidth - 8)}" value="${roi.x}"></label>
          <label>Y<input type="number" data-roi-field="y" min="0" max="${Math.max(0, state.imageHeight - 8)}" value="${roi.y}"></label>
          <label>W<input type="number" data-roi-field="width" min="8" max="${Math.max(8, state.imageWidth - roi.x)}" value="${roi.width}"></label>
          <label>H<input type="number" data-roi-field="height" min="8" max="${Math.max(8, state.imageHeight - roi.y)}" value="${roi.height}"></label>
        </div>` : ''}
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
      item.querySelectorAll('[data-roi-field]').forEach(input => {
        input.addEventListener('click', event => event.stopPropagation());
        const applyCoordinate = (event, rerender) => {
          event.stopPropagation();
          const roi = state.rois.find(candidate => candidate.id === roiId);
          if (!roi) return;
          const field = event.target.dataset.roiField;
          const value = Math.round(safeNumber(event.target.value, roi[field]));
          if (field === 'x') roi.x = Math.max(0, Math.min(state.imageWidth - roi.width, value));
          if (field === 'y') roi.y = Math.max(0, Math.min(state.imageHeight - roi.height, value));
          if (field === 'width') roi.width = Math.max(8, Math.min(state.imageWidth - roi.x, value));
          if (field === 'height') roi.height = Math.max(8, Math.min(state.imageHeight - roi.y, value));
          markDirty();
          if (rerender) renderRoiList();
          else item.querySelector('.empty-rack-roi-coords').textContent = `x=${roi.x}, y=${roi.y}, w=${roi.width}, h=${roi.height}`;
          drawScene();
        };
        input.addEventListener('input', event => applyCoordinate(event, false));
        input.addEventListener('change', event => applyCoordinate(event, true));
      });
    });
    updateProgress();
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
    renderRoiList();
    drawScene();
    updateProgress();
  }

  function loadImageUrl(url, sourceLabel, coordinateWidth, coordinateHeight) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => {
        showImage(image, sourceLabel, coordinateWidth, coordinateHeight);
        resolve(image);
      };
      image.onerror = () => reject(new Error('ROI 示教图加载失败'));
      image.src = url;
    });
  }

  function renderRecipeSelect() {
    const select = byId('empty-rack-recipe-select');
    if (!select) return;
    select.replaceChildren(new Option('＋ 新建空箱配方', ''));
    state.recipes.forEach(recipe => {
      select.add(new Option(
        `${recipe.is_active ? '●' : '○'} ${recipe.name}${recipe.is_active ? '（已发布）' : '（草稿）'}`,
        String(recipe.id),
      ));
    });
    select.value = state.recipe?.id ? String(state.recipe.id) : '';
  }

  async function loadRecipeList() {
    try {
      const response = await fetch(`${config.listUrl}?recipe_type=EMPTY_RACK_2D`);
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '配方列表读取失败');
      state.recipes = data.recipes || [];
      renderRecipeSelect();
    } catch (error) {
      const select = byId('empty-rack-recipe-select');
      if (select) select.innerHTML = '<option value="">配方列表读取失败</option>';
    }
  }

  function resetRecipeImage() {
    state.image = null;
    state.imageFile = null;
    state.captureToken = '';
    state.sourceRecord = null;
    state.imageWidth = 0;
    state.imageHeight = 0;
    context.clearRect(0, 0, canvas.width, canvas.height);
    canvas.style.display = 'none';
    byId('empty-rack-canvas-empty').style.display = 'flex';
    byId('empty-rack-image-meta').textContent = '请使用料架相机拍照或导入现场图片';
  }

  async function applyRecipe(recipe) {
    state.recipe = recipe || null;
    state.imageFile = null;
    state.captureToken = '';
    state.dirty = false;
    state.trialCompleted = Boolean(recipe?.is_active);
    state.published = Boolean(recipe?.is_active);
    renderTrialResult(null, recipe?.is_active ? '当前为已发布版本；计算预览与保存配方互不依赖。' : '尚未计算');
    if (!recipe) {
      resetRecipeImage();
      state.rois = [];
      state.selectedId = null;
      byId('empty-rack-name').value = '新建空箱检测配方';
      byId('empty-rack-brightness-threshold').value = .55;
      byId('empty-rack-foam-area-threshold').value = .03;
      byId('empty-rack-remark').value = '';
      renderRoiList();
      renderRecipeSelect();
      setSaveState('新草稿', false);
      setMessage('请先载入一张现场示教图，再拖拽绘制并命名检测区域。');
      updateProgress();
      return;
    }
    const teachingSource = recipe.algorithm_config?.teaching_source || recipe.algorithm_config?.reference_source;
    state.sourceRecord = teachingSource?.type === 'foam_inspection_record'
      ? {...teachingSource}
      : null;
    state.rois = Array.isArray(recipe.roi_config?.regions)
      ? recipe.roi_config.regions.map(roi => ({...roi}))
      : [];
    state.selectedId = state.rois[0]?.id || null;
    byId('empty-rack-name').value = recipe.name || '2D 空箱检测配方';
    byId('empty-rack-brightness-threshold').value = safeNumber(recipe.threshold_config?.foam_brightness_threshold, .55);
    byId('empty-rack-foam-area-threshold').value = safeNumber(
      recipe.threshold_config?.min_foam_area_ratio ?? recipe.threshold_config?.min_changed_area_ratio,
      .03,
    );
    byId('empty-rack-remark').value = recipe.remark || '';
    renderRoiList();
    const teachingImageUrl = recipe.teaching_image_url || recipe.reference_image_url;
    if (teachingImageUrl) {
      const sourceLabel = state.sourceRecord
        ? `泡棉检测记录 #${state.sourceRecord.record_id || '-'} · POS ${state.sourceRecord.position_index ?? '-'}`
        : '已保存 ROI 示教图';
      await loadImageUrl(`${teachingImageUrl}?v=${encodeURIComponent(recipe.updated_at || '')}`, sourceLabel);
    } else {
      resetRecipeImage();
    }
    renderRecipeSelect();
    setSaveState(recipe.is_active ? '已发布 · 可修改' : '草稿已保存 · 可修改', recipe.is_active);
    setMessage(`已加载“${recipe.name}”，共 ${state.rois.length} 个检测区域。`, 'success');
    updateProgress();
  }

  async function loadRecipe(recipeId = null, force = false) {
    if (state.loading || (state.loaded && !force && recipeId === null)) return;
    if (config.newRecipe && recipeId === null && !force) {
      state.loaded = true;
      await applyRecipe(null);
      await loadRecipeList();
      return;
    }
    state.loading = true;
    setMessage('正在读取空箱检测配方…');
    try {
      const requestedId = recipeId || new URLSearchParams(window.location.search).get('recipe_id');
      const detailUrl = requestedId
        ? `${config.detailUrl}?id=${encodeURIComponent(requestedId)}`
        : config.detailUrl;
      const response = await fetch(detailUrl);
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '读取配方失败');
      await applyRecipe(data.recipe || null);
      state.loaded = true;
      await loadRecipeList();
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
    const selected = state.rois.find(roi => roi.id === state.selectedId);
    const resizeHandle = handleAt(point, selected);
    if (selected && resizeHandle) {
      state.interaction = {
        type: 'resize', handle: resizeHandle, start: point,
        roiId: selected.id, original: {...selected},
      };
    } else {
      const hit = roiAt(point);
      if (hit) {
        state.selectedId = hit.id;
        state.interaction = {type: 'move', start: point, roiId: hit.id, original: {...hit}};
        renderRoiList();
      } else {
        state.selectedId = null;
        state.interaction = {type: 'draw', start: point, current: point};
      }
    }
    drawScene();
  });

  canvas.addEventListener('pointermove', event => {
    const point = canvasPoint(event);
    if (!state.interaction) {
      const selected = state.rois.find(roi => roi.id === state.selectedId);
      const handle = handleAt(point, selected);
      const cursors = {nw: 'nwse-resize', se: 'nwse-resize', ne: 'nesw-resize', sw: 'nesw-resize'};
      canvas.style.cursor = handle ? cursors[handle] : (roiAt(point) ? 'move' : 'crosshair');
      return;
    }
    if (state.interaction.type === 'draw') {
      state.interaction.current = point;
      drawScene();
      return;
    }
    const roi = state.rois.find(candidate => candidate.id === state.interaction.roiId);
    if (!roi) return;
    const original = state.interaction.original;
    const dx = point.x - state.interaction.start.x;
    const dy = point.y - state.interaction.start.y;
    if (state.interaction.type === 'move') {
      roi.x = Math.round(Math.max(0, Math.min(canvas.width - original.width, original.x + dx)));
      roi.y = Math.round(Math.max(0, Math.min(canvas.height - original.height, original.y + dy)));
    } else {
      let left = original.x;
      let top = original.y;
      let right = original.x + original.width;
      let bottom = original.y + original.height;
      if (state.interaction.handle.includes('w')) left = Math.max(0, Math.min(right - 8, original.x + dx));
      if (state.interaction.handle.includes('e')) right = Math.min(canvas.width, Math.max(left + 8, original.x + original.width + dx));
      if (state.interaction.handle.includes('n')) top = Math.max(0, Math.min(bottom - 8, original.y + dy));
      if (state.interaction.handle.includes('s')) bottom = Math.min(canvas.height, Math.max(top + 8, original.y + original.height + dy));
      roi.x = Math.round(left);
      roi.y = Math.round(top);
      roi.width = Math.round(right - left);
      roi.height = Math.round(bottom - top);
    }
    drawScene();
  });

  canvas.addEventListener('pointerup', event => {
    if (!state.interaction) return;
    const interaction = state.interaction;
    const end = canvasPoint(event);
    state.interaction = null;
    if (interaction.type === 'draw') {
      const roi = normalizedRect(interaction.start, end);
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
    }
    markDirty();
    renderRoiList();
    drawScene();
  });

  canvas.addEventListener('pointercancel', () => {
    state.interaction = null;
    drawScene();
  });

  byId('empty-rack-upload-btn').addEventListener('click', () => byId('empty-rack-image-input').click());
  byId('empty-rack-image-input').addEventListener('change', async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (state.rois.length && !window.confirm('更换示教图会清空当前 ROI，是否继续？')) {
      event.target.value = '';
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    try {
      state.rois = [];
      state.selectedId = null;
      state.imageFile = file;
      state.captureToken = '';
      state.sourceRecord = null;
      await loadImageUrl(objectUrl, file.name);
      renderRoiList();
      markDirty();
      setMessage('示教图已载入，请在图上拖拽绘制检测区域。');
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
      state.sourceRecord = null;
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

  ['empty-rack-name', 'empty-rack-brightness-threshold', 'empty-rack-foam-area-threshold', 'empty-rack-remark']
    .forEach(id => byId(id).addEventListener('input', markDirty));

  byId('empty-rack-recipe-select')?.addEventListener('change', async event => {
    const nextId = event.target.value;
    if (state.dirty && !window.confirm('切换配方会丢失当前未保存修改，是否继续？')) {
      event.target.value = state.recipe?.id ? String(state.recipe.id) : '';
      return;
    }
    if (!nextId) {
      await applyRecipe(null);
      window.history.replaceState({}, '', `${window.location.pathname}?mode=empty_rack&new=1`);
      return;
    }
    await loadRecipe(nextId, true);
    window.history.replaceState({}, '', `${window.location.pathname}?mode=empty_rack&recipe_id=${encodeURIComponent(nextId)}`);
  });

  async function importRecordImage(file, record = {}) {
    if (!file) return false;
    if (state.rois.length && !window.confirm('从检测记录更换示教图会清空当前 ROI，是否继续？')) return false;
    const objectUrl = URL.createObjectURL(file);
    try {
      state.rois = [];
      state.selectedId = null;
      state.imageFile = file;
      state.captureToken = '';
      state.sourceRecord = {
        type: 'foam_inspection_record',
        record_id: String(record.id || ''),
        captured_at: String(record.time || ''),
        position_index: Number(record.pos || 0),
      };
      await loadImageUrl(
        objectUrl,
        `泡棉检测记录 #${state.sourceRecord.record_id || '-'} · POS ${state.sourceRecord.position_index}`,
      );
      renderRoiList();
      markDirty();
      setMessage('记录原图已作为 ROI 示教图载入，可直接绘制区域并试算泡棉占用。');
      return true;
    } catch (error) {
      setMessage(error.message, 'error');
      return false;
    } finally {
      URL.revokeObjectURL(objectUrl);
    }
  }

  async function saveRecipe(saveMode, {quiet = false} = {}) {
    if (!state.image) {
      setMessage('请先载入一张 ROI 示教图。', 'error');
      return null;
    }
    if (!state.rois.length) {
      setMessage('请至少绘制一个检测 ROI。', 'error');
      return null;
    }
    const button = saveMode === 'draft' ? byId('empty-rack-calculate-btn') : byId('empty-rack-save-btn');
    const form = new FormData();
    if (state.recipe?.id) form.append('id', state.recipe.id);
    if (!state.recipe?.id) form.append('create_new', '1');
    form.append('save_mode', saveMode);
    if (state.imageFile) form.append('teaching_image', state.imageFile, state.imageFile.name);
    if (state.captureToken) form.append('preview_capture_token', state.captureToken);
    if (state.sourceRecord) form.append('teaching_source', JSON.stringify(state.sourceRecord));
    form.append('name', byId('empty-rack-name').value.trim() || '2D 空箱检测配方');
    form.append('image_width', state.imageWidth);
    form.append('image_height', state.imageHeight);
    form.append('regions', JSON.stringify(state.rois));
    form.append('foam_brightness_threshold', byId('empty-rack-brightness-threshold').value);
    form.append('min_foam_area_ratio', byId('empty-rack-foam-area-threshold').value);
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
      const published = saveMode === 'publish';
      state.dirty = false;
      state.published = published;
      if (published) state.trialCompleted = true;
      setSaveState(published ? '已发布' : '草稿已保存', published);
      if (!quiet) {
        setMessage(`${published ? '配方保存并发布' : '参数暂存'}成功：${state.rois.length} 个 ROI 已写入配方。`, 'success');
      }
      renderRoiList();
      await loadRecipeList();
      updateProgress();
      if (!quiet && typeof window.showToast === 'function') window.showToast('空箱检测配方保存成功', 'success');
      return data.recipe;
    } catch (error) {
      setMessage(error.message, 'error');
      if (typeof window.showToast === 'function') window.showToast(error.message, 'error');
      return null;
    } finally {
      button.disabled = false;
      button.textContent = saveMode === 'draft' ? '开始计算' : '保存配方';
    }
  }

  async function runTrial({file = null, previewCaptureToken = ''} = {}) {
    if (!state.image) return setMessage('请先载入左侧示教图。', 'error');
    if (!state.rois.length) return setMessage('请至少绘制一个检测 ROI。', 'error');
    const form = new FormData();
    if (state.recipe?.id) form.append('recipe_id', state.recipe.id);
    const currentFile = file || state.imageFile;
    const currentCaptureToken = previewCaptureToken || state.captureToken;
    if (currentFile) form.append('image', currentFile, currentFile.name);
    else if (currentCaptureToken) form.append('preview_capture_token', currentCaptureToken);
    else form.append('use_teaching_image', '1');
    form.append('regions', JSON.stringify(state.rois));
    form.append('foam_brightness_threshold', byId('empty-rack-brightness-threshold').value);
    form.append('min_foam_area_ratio', byId('empty-rack-foam-area-threshold').value);
    renderTrialResult(null, '正在逐 ROI 识别泡棉占用…');
    try {
      const response = await fetch(config.inspectUrl, {
        method: 'POST',
        headers: {'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''},
        body: form,
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '试跑计算失败');
      state.trialCompleted = true;
      renderTrialResult(data.result);
      setMessage(
        `计算完成：${data.result.is_empty ? '判定为空箱' : `发现 ${data.result.occupied_count} 个异常区域`}，确认后可保存配方。`,
        data.result.is_empty ? 'success' : '',
      );
      return data.result;
    } catch (error) {
      state.trialCompleted = false;
      renderTrialResult(null, error.message);
      setMessage(error.message, 'error');
      return null;
    }
  }

  byId('empty-rack-calculate-btn')?.addEventListener('click', async () => {
    const button = byId('empty-rack-calculate-btn');
    button.disabled = true;
    button.textContent = '计算中…';
    renderTrialResult(null, '正在使用左侧当前图像逐 ROI 计算…');
    setMessage('正在根据左侧图像和当前参数计算，不会保存或改变配方状态…');
    try {
      await runTrial();
    } catch (error) {
      renderTrialResult(null, error.message);
      setMessage(error.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = '开始计算';
    }
  });

  byId('empty-rack-save-btn').addEventListener('click', () => {
    saveRecipe('publish');
  });

  document.querySelector('[data-recipe-tab="empty2d"]')?.addEventListener('click', loadRecipe);
  window.EmptyRackRecipeEditor = {load: loadRecipe, importRecordImage, runTrial};

  const requestedTab = new URLSearchParams(window.location.search).get('tab');
  if (requestedTab === 'empty2d') {
    document.querySelector('[data-recipe-tab="empty2d"]')?.click();
  } else if (config.autoLoad) {
    loadRecipe();
  }
})();
