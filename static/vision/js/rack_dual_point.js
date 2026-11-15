/* Point-cloud template ROI editor. Reuses the workbench frame snapshot. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const panel = $('dp-panel');
  if (!panel) return;
  const canvas = $('dp-canvas'), ctx = canvas.getContext('2d');
  const depthCanvas = $('dp-depth-canvas'), depthCtx = depthCanvas.getContext('2d');
  const targets = ['P1_cross', 'P2_cross'];
  const labels = ['模板区域 1 · 交叉位置', '模板区域 2 · 交叉位置'];
  const algorithm = () => 'cloud_center';
  const regionLabel = index => `模板区域 ${index + 1}`;
  const centerLabel = index => {
    const stage = state.result?.registration ? (state.result.success ? '匹配中心' : '候选中心') : '基准中心';
    return `区域 ${index + 1} ${stage}`;
  };
  const colors = ['#facc15', '#38bdf8', '#4ade80', '#e879f9'];
  const state = {config: null, image: null, depthImage: null, captureTokenBefore: null, prepared: null, selected: 0, result: null, drag: null, busy: false, revision: 0,
    evaluation: null, teachToken: null, reference: null, forensicFrame: null, capturing: false, dirty: false, redraw: false};
  let saveFeedback = '';
  let recipeReloadPending = false;
  const recipeId = () => String($('recipe-select')?.value || $('recipe-id')?.value || '');
  const pointNames = () => Number(state.config?.rack_layers || $('dp-rack-layers').value) === 2 ? ['P1'] : ['P1', 'P2'];
  const activeTargets = () => targets.slice(0, pointNames().length);
  const roi = () => state.config?.rois.find(r => r.target === targets[state.selected]);
  const status = text => { $('dp-status').textContent = text; };
  const currentFrame = () => window.rackLocatorOfflineBridge?.snapshot();
  // Frame snapshots also contain saved template points and old results. Those
  // can exceed Django's request limit; the server already owns that data.
  const frameRequest = (snapshot = currentFrame()) => ({
    pointcloud_token: snapshot?.pointcloud_token,
    source: snapshot?.source,
    package_library: snapshot?.package_library,
    raw_rgb_image_url: snapshot?.raw_rgb_image_url,
    recipe_id: snapshot?.recipe_id,
    layer_no: snapshot?.layer_no,
  });
  const fmt = (value, digits = 3) => {
    if (!Number.isFinite(value)) return '—';
    const rounded = value.toFixed(digits);
    return Number(rounded) === 0 ? (0).toFixed(digits) : rounded;
  };
  // Show native camera XYZ in the same axis order and signs as the measurement.
  const xyz = values => Array.isArray(values) ? values.map(v => fmt(v)).join(' / ') : '—';
  function cell(row, text, header = false) {
    const item = document.createElement(header ? 'th' : 'td'); item.textContent = text; row.appendChild(item); return item;
  }
  function renderResults() {
    window.rackResultTables.render(panel, state.evaluation, state.reference?.measurement, pointNames());
  }
  function checkFrame() {
    if (!state.prepared || state.prepared.recipe_id !== recipeId() ||
        state.prepared.frame !== currentFrame()?.pointcloud_token) {
      throw new Error('当前配方或采集帧已变化，请点击「载入当前原图」后再操作。');
    }
  }
  async function request(url, body) {
    const response = await fetch(url, {method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || ''},
      body: JSON.stringify(body)});
    let data;
    try { data = await response.json(); } catch (_) {
      throw new Error(`接口未返回有效 JSON（HTTP ${response.status}）：${url}。请检查服务端错误日志。`);
    }
    if (!response.ok || !data.success) {
      const error = new Error([data.errorCode, data.errorMessage || data.error].filter(Boolean).join('：'));
      error.stage = data.stage; error.code = data.errorCode;
      throw error;
    }
    return data;
  }
  function refresh() {
    $('dp-save-standard').disabled = state.busy || state.capturing || (!state.prepared || !recipeId() || activeTargets().some(target => !state.config?.rois.some(r => r.target === target)) || state.redraw || !!state.drag);
    $('dp-save-standard').textContent = '保存当前帧为点云标准模板';
    panel.querySelectorAll('#dp-camera-results thead tr th:first-child, #dp-robot-results-panel thead tr th:first-child').forEach(th => {th.textContent = '模板区域';});
    $('dp-empty').querySelector('small').textContent = '框选稳定结构区域，保存标准点云后进行匹配';
    $('dp-rack-layers').disabled = state.busy || state.capturing || !!state.drag;
    $('dp-mode-help').textContent = `模板中心匹配：每个交叉位置画一个框，同时包含横杆、立柱和连接处。各区域共同组成一个模板。需画 ${activeTargets().length} 个框；修改层数或框选后需重新保存点云模板。`;
    $('dp-targets').querySelectorAll('button').forEach((button, index) => {
      button.hidden = index >= activeTargets().length;
      button.textContent = labels[index] + (state.config?.rois.some(r => r.target === targets[index]) ? ' ✓' : '');
      button.style.outline = index === state.selected ? `2px solid ${colors[index]}` : '';
      button.disabled = state.busy || state.capturing;
    });
    // Keep validation failures clickable so the user can see why saving is blocked.
    // Selecting an existing ROI only arms redraw; it does not invalidate its saved box.
    $('dp-save-recipe').disabled = state.busy || state.capturing || !!state.drag;
    $('dp-save-recipe').textContent = saveFeedback === '正在保存…' ? '正在保存…' : '保存配方';
    $('dp-draft-status').textContent = saveFeedback || (state.dirty ? '草稿 · 未保存到配方' : state.config ? '已载入配方' : '请先载入图像和 ROI');
    $('dp-evaluate').disabled = state.busy || state.capturing;

  }

  function edited() {
    saveFeedback = '';
    state.dirty = true;
    state.revision++;
    state.result = null;
    state.evaluation = null; state.teachToken = null; state.reference = null;

    status(`ROI 已框选 ${state.config.rois.length}/${activeTargets().length}，已暂存为草稿，点击「保存配方」写入当前配方。`);
    refresh(); draw(); renderResults();
  }
  function drawDepth() {
    depthCtx.clearRect(0, 0, depthCanvas.width, depthCanvas.height);
    depthCanvas.hidden = !state.depthImage;
    if (!state.depthImage) return;
    depthCtx.drawImage(state.depthImage, 0, 0);
    const unit = depthCanvas.width / (depthCanvas.getBoundingClientRect().width || depthCanvas.width);
    depthCtx.font = `${16*unit}px sans-serif`;
    state.config?.rois.forEach(r => {
      const index = targets.indexOf(r.target);
      if (index < 0) return;
      depthCtx.strokeStyle = colors[index]; depthCtx.fillStyle = colors[index]; depthCtx.lineWidth = 2*unit;
      depthCtx.strokeRect(r.x, r.y, r.width, r.height);
      depthCtx.fillText(regionLabel(index), r.x+4*unit, r.y+16*unit);
    });
    state.result?.pixels?.forEach((pixel, index) => {
      if (!pixel?.every(Number.isFinite)) return;
      const [x, y] = pixel;
      depthCtx.strokeStyle = '#fff'; depthCtx.fillStyle = '#fff'; depthCtx.lineWidth = 2*unit;
      depthCtx.beginPath(); depthCtx.arc(x, y, 6*unit, 0, Math.PI*2);
      depthCtx.moveTo(x-12*unit, y); depthCtx.lineTo(x+12*unit, y);
      depthCtx.moveTo(x, y-12*unit); depthCtx.lineTo(x, y+12*unit); depthCtx.stroke();
      depthCtx.fillText(centerLabel(index), x+14*unit, y-10*unit);
    });
  }
  async function loadDepth(data, prepared) {
    state.depthImage = null; drawDepth();
    $('dp-depth-source').textContent = '正在生成对应点云伪彩图…';
    try {
      const img = new Image(); img.src = data.depth_preview_url; await img.decode();
      if (state.prepared !== prepared) return;
      if (img.naturalWidth !== canvas.width || img.naturalHeight !== canvas.height) throw new Error('原图与点云尺寸不一致');
      depthCanvas.width = canvas.width; depthCanvas.height = canvas.height;
      state.depthImage = img;
      $('dp-depth-source').textContent = data.pointcloud_name;
      drawDepth();
    } catch (error) {
      if (state.prepared !== prepared) return;
      state.depthImage = null; drawDepth();
      $('dp-depth-source').textContent = `点云预览未完成：${error.message}`;
    }
  }
  function draw() {
    drawDepth();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!state.image) return;
    ctx.drawImage(state.image, 0, 0);
    const unit = canvas.width / (canvas.getBoundingClientRect().width || canvas.width);
    state.config?.rois.forEach(r => {
      const index = targets.indexOf(r.target);
      if (index < 0) return;
      ctx.strokeStyle = colors[index]; ctx.lineWidth = (index === state.selected ? 3 : 2)*unit;
      ctx.strokeRect(r.x, r.y, r.width, r.height);
      ctx.fillStyle = colors[index]; ctx.font = `${17*unit}px sans-serif`;
      ctx.fillText(regionLabel(index), r.x+4*unit, r.y+16*unit);
      if (index === state.selected) ctx.fillRect(r.x+r.width-5*unit, r.y+r.height-5*unit, 10*unit, 10*unit);
    });
    state.result?.pixels?.forEach((pixel, index) => {
      if (!pixel?.every(Number.isFinite)) return;
      const [x, y] = pixel;
      ctx.strokeStyle = '#ff3030'; ctx.lineWidth = 2*unit; ctx.beginPath();
      ctx.moveTo(x-12*unit,y); ctx.lineTo(x+12*unit,y); ctx.moveTo(x,y-12*unit); ctx.lineTo(x,y+12*unit); ctx.stroke();
      ctx.font = `${17*unit}px sans-serif`;
      ctx.fillStyle = '#ff3030'; ctx.fillText(centerLabel(index),x+15*unit,y);
    });
  }

  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return {x: Math.max(0, Math.min(canvas.width, (event.clientX-rect.left)*canvas.width/rect.width)),
            y: Math.max(0, Math.min(canvas.height, (event.clientY-rect.top)*canvas.height/rect.height))};
  }
  // Pixel coordinates are diagnostic hover text, separate from camera XYZ (mm).
  [canvas, depthCanvas].forEach(surface => {
    surface.addEventListener('pointermove', event => {
      if (state.drag) { surface.title = ''; return; }
      const rect = surface.getBoundingClientRect();
      const x = (event.clientX - rect.left) * surface.width / rect.width;
      const y = (event.clientY - rect.top) * surface.height / rect.height;
      const radius = 16 * surface.width / rect.width;
      const index = state.result?.pixels?.findIndex(pixel => pixel?.every(Number.isFinite)
        && Math.hypot(pixel[0] - x, pixel[1] - y) <= radius) ?? -1;
      const pixel = state.result?.pixels?.[index];
      surface.title = index < 0 ? '' : `${centerLabel(index)} · 图像像素坐标 (${pixel[0].toFixed(2)}, ${pixel[1].toFixed(2)}) px`;
    });
    surface.addEventListener('pointerleave', () => { surface.title = ''; });
  });
  labels.forEach((label, index) => {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'btn btn-secondary';
    button.style.borderColor = colors[index]; button.textContent = label;
    button.addEventListener('click', () => action(async () => {
      if (!state.prepared || state.prepared.recipe_id !== recipeId() || state.prepared.frame !== currentFrame()?.pointcloud_token) await loadFrame();
      checkFrame(); state.selected = index; state.redraw = true;
      status(`请拖动重画 ${labels[index]}，画完暂存为草稿，再点击「保存配方」。`);
      refresh(); draw();
    }));
    $('dp-targets').appendChild(button);
  });
  canvas.addEventListener('pointerdown', event => {
    if (!state.image || state.busy || event.button !== 0) return;
    try { checkFrame(); } catch (error) { status(error.message); return; }
    const p = point(event), r = roi(), tolerance = 10*canvas.width/canvas.getBoundingClientRect().width;
    const resize = r && Math.abs(p.x-r.x-r.width)<tolerance && Math.abs(p.y-r.y-r.height)<tolerance;
    const inside = r && p.x>=r.x && p.x<=r.x+r.width && p.y>=r.y && p.y<=r.y+r.height;
    state.drag = {start: p, original: r ? {...r} : null, mode: state.redraw ? 'new' : resize ? 'resize' : inside ? 'move' : 'new'};
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointermove', event => {
    if (!state.drag) return;
    const p = point(event), {start, original, mode} = state.drag;
    let box;
    if (mode === 'move') {
      box = {...original, x: Math.max(0, Math.min(canvas.width-original.width, original.x+p.x-start.x)),
             y: Math.max(0, Math.min(canvas.height-original.height, original.y+p.y-start.y))};
    } else if (mode === 'resize') {
      box = {...original, width: Math.max(3, p.x-original.x), height: Math.max(3, p.y-original.y)};
    } else {
      box = {...(original || {}), id: `roi${state.selected+1}`, target: targets[state.selected],
             x: Math.min(p.x,start.x), y: Math.min(p.y,start.y), width: Math.abs(p.x-start.x), height: Math.abs(p.y-start.y)};

    }
    state.config.rois = state.config.rois.filter(r => r.target !== box.target).concat(box);
    edited();
  });
  function endDrag() {
    if (!state.drag) return;
    state.drag = null; state.redraw = false;
    state.config.rois = state.config.rois.filter(r => r.width >= 3 && r.height >= 3);
    edited();
  }
  canvas.addEventListener('pointerup', endDrag);
  canvas.addEventListener('pointercancel', endDrag);
  canvas.addEventListener('lostpointercapture', endDrag);
  async function action(fn) {
    if (state.busy) return;
    state.busy = true; refresh();
    try {await fn(); return true;} catch (error) {
      state.result = {success: false, stage: error.stage, errorCode: error.code, errorMessage: error.message};
      state.evaluation = {result: state.result}; state.teachToken = null;
      draw(); status(error.message);
      return false;
    }
    finally {
      state.busy = false; refresh(); renderResults();
      if (recipeReloadPending && !state.capturing) {
        recipeReloadPending = false;
        if (currentFrame()?.pointcloud_token) await action(loadFrame);
      }
    }
  }
  async function loadFrame() {
    saveFeedback = '';
    const snapshot = currentFrame(), selectedRecipe = recipeId();
    if (!snapshot?.pointcloud_token) throw new Error('请先点击「采集点云」。');
    status('正在读取相机原图和已保存的ROI…');
    const data = await request(panel.dataset.prepareUrl, {...frameRequest(snapshot), recipe_id: selectedRecipe, algorithm: algorithm()});
    const img = new Image(); img.src = data.image_url; await img.decode();
    if (selectedRecipe !== recipeId() || snapshot.pointcloud_token !== currentFrame()?.pointcloud_token) throw new Error('加载期间配方或采集帧变化，请重新载入。');
    state.dirty = false; state.redraw = false;
    state.image = img; state.config = data.config;
    state.config.rack_layers = data.config.rack_layers || (data.config.rois.length ? 3 : Number($('dp-rack-layers').value));
    $('dp-rack-layers').value = String(state.config.rack_layers);
    state.selected = 0; state.result = null; state.evaluation = null; state.teachToken = null; state.reference = data.reference;
    state.prepared = {image_token: data.image_token, cloud_token: data.cloud_token, recipe_id: selectedRecipe, frame: snapshot.pointcloud_token};
    canvas.width = data.width; canvas.height = data.height; canvas.hidden = false; canvas.style.display = 'block';
    $('dp-empty').hidden = true;
    if (JSON.stringify(state.config.imageSize) !== JSON.stringify([data.width, data.height])) {
      state.config.rois = []; state.config.imageSize = [data.width, data.height];
      status('原图尺寸与已存 ROI 不同，已清除本地框选，请重新绘制后保存。');
    } else status(`原图 ${data.width} × ${data.height}，配方 #${selectedRecipe || '未选择'}。ROI 已载入 ${state.config.rois.length}/${activeTargets().length}。\n${data.three_d_status}`);
    state.revision++; refresh(); draw();
    void loadDepth(data, state.prepared);
  }
  $('dp-save-recipe').addEventListener('click', () => action(async () => {
    try {
      if (!recipeId()) throw new Error('请先选择配方。');
      if (!state.prepared || !state.config) throw new Error('请先采集或加载点云，再框选 ROI。');
      checkFrame();
      const selectedRecipe = recipeId(), revision = state.revision;
      const missing = activeTargets().filter(target => !state.config.rois.some(r => r.target === target));
      if (missing.length) throw new Error(`尚缺 ${missing.map(target => labels[targets.indexOf(target)]).join('、')}，请完成后保存。`);
      if (state.drag) throw new Error('请先松开鼠标，结束框选。');
      saveFeedback = '正在保存…'; refresh();
      const saved = await request(panel.dataset.saveUrl, {...state.prepared, recipe_id: selectedRecipe, config: state.config});
      checkFrame();
      if (revision !== state.revision) throw new Error('保存期间草稿发生变化，请重新保存。');
      state.config = saved.config || state.config;
      state.dirty = false; state.redraw = false;
      const name = $('recipe-select')?.selectedOptions?.[0]?.textContent.trim() || selectedRecipe;
      saveFeedback = '已保存到配方';
      status(`ROI 已保存到配方「${name}」。框选配置已保存；点云标准模板需另点「保存当前帧为点云标准模板」。`);
    } catch (error) {
      saveFeedback = `保存失败：${error.message}`;
      status(saveFeedback);
    }
  }));
  $('dp-evaluate').addEventListener('click', () => action(async () => {
    if (!state.prepared || state.prepared.recipe_id !== recipeId() || state.prepared.frame !== currentFrame()?.pointcloud_token) await loadFrame();
    checkFrame(); state.result = null; state.evaluation = null; state.teachToken = null;
    if (!state.reference) {
      status('请先加载基准点云，每个交叉位置画一个 ROI，点击「保存当前帧为点云标准模板」。保存配方仅保存框选配置，不会建立点云模板。');
      draw(); renderResults(); return;
    }
    draw(); renderResults();
    status('正在进行点云多尺度 ICP 匹配…');
    const revision = state.revision;
    const data = await request(panel.dataset.cloudMatchUrl, {...frameRequest(), ...state.prepared, config: state.config, coordinate_system: 'camera'});
    checkFrame(); if (revision !== state.revision) throw new Error('配置变化，请重新校验。');
    state.result = data.result; state.evaluation = data; state.teachToken = data.teach_token; state.reference = data.reference;
    draw();
    status(data.is_success === false ? [data.failure_reason, ...(data.result.registration?.failure_reasons || [])].filter(Boolean).join("；") : data.result.registration
      ? data.result.success ? '匹配通过，坐标与偏差见右侧。'
        : `匹配未通过：${(data.result.registration.failure_reasons || ['请展开匹配详情检查']).join('；')}。当前仅显示候选位置。`
      : data.result.success ? ['相机坐标已计算，右侧显示与标准模板的差值。', ...(data.result.warnings || [])].join('\n') : `${data.result.errorCode}：${data.result.errorMessage}`);

  }));
  $('dp-save-standard').addEventListener('click', () => action(async () => {
    checkFrame();
    const selectedRecipe = recipeId(), revision = state.revision;
    const data = await request(panel.dataset.cloudMatchUrl, {...frameRequest(), ...state.prepared, recipe_id: selectedRecipe, config: state.config, action: 'save_template'});
    state.result = data.result; state.evaluation = data;
    checkFrame();
    if (revision !== state.revision || selectedRecipe !== recipeId()) return;
    state.reference = data.reference;
    if (state.evaluation) state.evaluation.robot_result = data.robot_result;
    state.config = data.config || state.config;
    state.dirty = false;
    state.teachToken = null;
    draw();
    const name = $('recipe-select')?.selectedOptions?.[0]?.textContent.trim() || selectedRecipe;
    status(`点云标准模板已保存到配方「${name}」。请加载待测帧后开始计算。`);
  }));
  function invalidateFrame() {
    saveFeedback = '';
    state.dirty = false; state.redraw = false;
    state.revision++; state.result = null; state.evaluation = null; state.teachToken = null; state.reference = null; state.drag = null;
    state.prepared = null; state.image = null; state.config = null; state.depthImage = null;
    $('dp-depth-source').textContent = '采集或导入后显示对应点云';
    canvas.hidden = true; canvas.style.display = 'none'; $('dp-empty').hidden = false;

    status('采集点云后点击「开始计算」，自动载入原图与配方 ROI。'); refresh(); draw(); renderResults();
  }
  $('dp-rack-layers').addEventListener('change', () => {
    state.selected = 0; state.redraw = false;
    if (state.config) {
      state.config.rack_layers = Number($('dp-rack-layers').value);
      state.config.rois = state.config.rois.filter(r => activeTargets().includes(r.target));
      edited();
      status('料架层数已修改，请完成框选并重新保存点云标准模板。');
    } else { refresh(); renderResults(); }
  });
  $('recipe-select')?.addEventListener('change', () => {
    $('dp-rack-layers').value = '3';
    invalidateFrame();
    // The source frame is independent of the recipe. Reload its canvas with
    // the newly selected recipe's ROI/reference instead of discarding the view.
    recipeReloadPending = !!currentFrame()?.pointcloud_token;
    if (recipeReloadPending && !state.busy && !state.capturing) {
      recipeReloadPending = false;
      void action(loadFrame);
    }
  });
  $('btn-capture')?.addEventListener('click', () => {
    state.captureTokenBefore = currentFrame()?.pointcloud_token;
    invalidateFrame(); state.capturing = true; refresh(); $('dp-frame-status').textContent = '正在采集相机数据…';
  });
  function finishCapture() {
    if (!state.capturing || $('btn-capture').disabled) return;
    state.capturing = false; refresh();
    const token = currentFrame()?.pointcloud_token;
    if (token && token !== state.captureTokenBefore) void action(loadFrame);
  }
  new MutationObserver(() => {
    if (state.capturing) {
      $('dp-frame-status').textContent = $('rl-status').textContent;
      finishCapture();
    }
  }).observe($('rl-status'), {childList:true, characterData:true, subtree:true});
  new MutationObserver(() => {
    finishCapture();
  }).observe($('btn-capture'), {attributes:true, attributeFilter:['disabled']});
  $('rl-depth-image')?.addEventListener('load', () => {
    if (state.prepared && state.prepared.frame !== currentFrame()?.pointcloud_token) invalidateFrame();
    else if (state.forensicFrame && state.forensicFrame !== currentFrame()?.pointcloud_token) invalidateFrame();
  });
  const bridge = window.rackLocatorOfflineBridge;
  if (bridge) {
    const originalSnapshot = bridge.snapshot.bind(bridge), originalLoad = bridge.load.bind(bridge);
    bridge.snapshot = () => {
      const snapshot = originalSnapshot();
      if ($('rack-workbench').dataset.mode !== 'dual') return snapshot;
      const current = state.prepared?.frame === snapshot.pointcloud_token && state.prepared?.recipe_id === recipeId();
      return {...snapshot, result: current ? state.evaluation?.result || null : null,
        roi_config: {...snapshot.roi_config, ...(current && state.config ? {[algorithm() + '_config']:state.config} : {})}};
    };
    bridge.load = async payload => {
      if (state.busy || state.capturing) throw new Error('当前操作尚未完成，请稍后重新加载数据包。');
      originalLoad(payload); invalidateFrame();
      $('dp-frame-status').textContent = '数据包已加载，正在自动载入原图与ROI…';
      // The prepare endpoint reads the original frame directly. A hidden preview
      // may fail or never emit load, and must not gate the actual canvas.
      if (!await action(loadFrame)) {
        const message = `加载画布失败：${$('dp-status').textContent}`;
        $('dp-frame-status').textContent = message;
        throw new Error(message);
      }
      $('dp-frame-status').textContent = '数据包原图与 ROI 已载入画布。';
    };
  }
  window.addEventListener('rack-cloud-result', event => {
    if (!state.prepared) return;
    const data = event.detail;
    state.result = data.result; state.evaluation = data; state.reference = data.reference;
    draw(); renderResults();
  });
  window.addEventListener('resize', draw);
  refresh(); renderResults();
})();
