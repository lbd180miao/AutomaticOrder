/* Isolated four-ROI editor. Reuses the workbench's existing frame snapshot. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const panel = $('dp-panel');
  if (!panel) return;
  const canvas = $('dp-canvas'), ctx = canvas.getContext('2d');
  const depthCanvas = $('dp-depth-canvas'), depthCtx = depthCanvas.getContext('2d');
  const targets = ['P1_horizontal', 'P1_vertical', 'P2_horizontal', 'P2_vertical'];
  const labels = ['ROI1 · P1 横杆', 'ROI2 · P1 立柱', 'ROI3 · P2 横杆', 'ROI4 · P2 立柱'];
  const colors = ['#facc15', '#38bdf8', '#4ade80', '#e879f9'];
  const state = {config: null, image: null, depthImage: null, captureTokenBefore: null, prepared: null, selected: 0, result: null, drag: null, busy: false, revision: 0,
    evaluation: null, teachToken: null, reference: null, forensicFrame: null, capturing: false, dirty: false, redraw: false};
  let saveFeedback = '';
  let selectedAlgorithm = null;
  const cloudMode = () => $('dp-localization-mode').value === 'cloud_match';
  const recipeId = () => String($('recipe-select')?.value || $('recipe-id')?.value || '');
  const roi = () => state.config?.rois.find(r => r.target === targets[state.selected]);
  const status = text => { $('dp-status').textContent = text; };
  const currentFrame = () => window.rackLocatorOfflineBridge?.snapshot();
  const fmt = (value, digits = 3) => Number.isFinite(value) ? value.toFixed(digits) : '—';
  // Show native camera XYZ in the same axis order and signs as the measurement.
  const xyz = values => Array.isArray(values) ? values.map(v => fmt(v)).join(' / ') : '—';
  function cell(row, text, header = false) {
    const item = document.createElement(header ? 'th' : 'td'); item.textContent = text; row.appendChild(item); return item;
  }
  function renderResults() {
    const result = state.result, reference = state.reference?.measurement;
    const body = $('dp-point-results'); body.replaceChildren();
    const validXYZ = values => Array.isArray(values) && values.length === 3 && values.every(Number.isFinite);
    // This table compares camera measurements, including comparisons between algorithms.
    // Algorithm/ROI digests gate robot compensation, not this arithmetic display.
    const compatible = result?.coordinateSystem === 'camera' && reference?.coordinateSystem === 'camera'
      && result?.success === true && reference?.success === true
      && result?.unit === 'mm' && reference?.unit === 'mm';
    for (const name of ['P1', 'P2']) {
      const standardPoint = reference?.points?.find(point => point.name === name);
      const currentPoint = result?.points?.find(point => point.name === name);
      const standard = reference?.coordinateSystem === 'camera' && reference?.success && standardPoint?.success ? standardPoint.xyz : null;
      const candidate = cloudMode() && result?.registration && !result.success;
      const current = result?.coordinateSystem === 'camera' && ((result?.success && currentPoint?.success) || candidate) ? currentPoint?.xyz : null;
      // Display measured coordinate differences only; PLC compensation retains its backend gates.
      const delta = compatible && validXYZ(standard) && validXYZ(current)
        ? current.map((value, axis) => value - standard[axis]) : null;
      const row = document.createElement('tr'); cell(row, `${name}${cloudMode() ? ' 区域参考点' : ''}${candidate ? '（候选）' : ''}`, true);
      [standard, current, delta].forEach(values => cell(row, validXYZ(values) ? xyz(values) : '—'));
      body.appendChild(row);
    }
    const quality = state.result?.registration;
    $('dp-match-details').hidden = !quality;
    $('dp-match-quality').textContent = quality ? [
      `匹配质量：${quality.quality_passed ? '通过（实验）' : '未通过，候选结果仅供查看'}`,
      ...(quality.failure_reasons || []).map(reason => `未通过原因：${reason}`),
      `模板覆盖率 ${(quality.fitness*100).toFixed(1)}% / 至少 ${(quality.limits.min_fitness*100).toFixed(0)}%；残差 ${fmt(quality.rmse_mm)}mm / 最多 ${quality.limits.max_rmse_mm}mm`,
      `中心位移 ${fmt(quality.shift_mm)}mm；旋转 ${fmt(quality.rotation_deg)}°；匹配点 ${quality.matched_points}/${quality.source_points}`,
      `结构约束比 ${quality.constraint_ratio.toFixed(6)} / 至少 0.0001`,
      '标准 → 当前变换矩阵：', ...quality.transform.map(row => row.map(v => fmt(v, 6)).join('  ')),
      ...(result.warnings || [])
    ].join('\n') : '';
    const robot = state.evaluation?.robot_result;
    const robotBody = $('dp-robot-results'); robotBody.replaceChildren();
    ['P1', 'P2'].forEach((name, index) => {
      const row = document.createElement('tr'); cell(row, name, true);
      for (let axis=0; axis<3; axis++) cell(row, robot?.success ? fmt(robot.offsets[index][axis]) : '—');
      robotBody.appendChild(row);
    });
    $('dp-robot-status').textContent = robot?.success
      ? ''
      : robot?.errorMessage || '计算后显示两组偏差。';
    $('dp-result-state').textContent = state.evaluation
      ? result?.registration ? (result.success ? '匹配通过' : '匹配未通过 · 候选结果')
        : result?.success ? '已计算' : `${({'2d':'二维找边失败', '3d':'三维测量失败', input:'输入校验失败', configuration:'配置校验失败', calibration:'标定校验失败'})[result?.stage] || '计算失败'}：${result?.errorMessage || result?.errorCode || '未知原因'}`
      : result ? '二维完成，待计算三维' : '待检测';
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
    const data = await response.json();
    if (!response.ok || !data.success) {
      const error = new Error([data.errorCode, data.errorMessage || data.error].filter(Boolean).join('：'));
      error.stage = data.stage; error.code = data.errorCode;
      throw error;
    }
    return data;
  }
  function refresh() {
    $('dp-auto-rois').disabled = cloudMode() || state.busy || state.capturing || !!state.drag || !state.prepared || !state.image;
    $('dp-save-standard').disabled = state.busy || state.capturing || (cloudMode()
      ? !state.prepared || !recipeId() || state.config?.rois.length !== 4 || state.redraw || !!state.drag
      : !state.teachToken || state.result?.coordinateSystem !== 'camera');
    $('dp-save-standard').textContent = cloudMode() ? '保存当前帧为点云标准模板' : '保存为标准模板';
    $('dp-localization-mode').disabled = state.busy || state.capturing;
    $('dp-algorithm').parentElement.hidden = cloudMode();
    panel.querySelectorAll('thead tr th:first-child').forEach(th => {th.textContent = cloudMode() ? '参考点' : '交点';});
    $('dp-empty').querySelector('small').textContent = cloudMode() ? '框选稳定结构区域，保存标准点云后进行匹配' : '在真实 2D 原图上测边，P1 / P2 将叠加在图上';
    $('dp-mode-help').textContent = cloudMode()
      ? '点云匹配：P1/P2 为区域参考点。修改框选后需重新保存点云模板。'
      : '四 ROI 找边：拟合横杆与立柱边缘交点，再读取三维坐标。';
    $('dp-targets').querySelectorAll('button').forEach((button, index) => {
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
    $('dp-algorithm').disabled = state.busy || state.capturing;

  }

  function edited() {
    saveFeedback = '';
    state.dirty = true;
    state.revision++;
    state.result = null;
    state.evaluation = null; state.teachToken = null; state.reference = null;

    status(`四 ROI 已框选 ${state.config.rois.length}/4，已暂存为草稿，点击「保存配方」写入当前配方。`);
    refresh(); draw(); renderResults();
  }
  function drawDepth() {
    depthCtx.clearRect(0, 0, depthCanvas.width, depthCanvas.height);
    depthCanvas.hidden = !state.depthImage;
    if (!state.depthImage) return;
    depthCtx.drawImage(state.depthImage, 0, 0);
    const unit = depthCanvas.width / (depthCanvas.getBoundingClientRect().width || depthCanvas.width);
    depthCtx.font = `${13*unit}px sans-serif`;
    state.config?.rois.forEach(r => {
      const index = targets.indexOf(r.target);
      if (index < 0) return;
      depthCtx.strokeStyle = colors[index]; depthCtx.fillStyle = colors[index]; depthCtx.lineWidth = 2*unit;
      depthCtx.strokeRect(r.x, r.y, r.width, r.height);
      depthCtx.fillText(`ROI${index+1}`, r.x+4*unit, r.y+16*unit);
    });
    state.result?.pixels?.forEach((pixel, index) => {
      if (!pixel?.every(Number.isFinite)) return;
      const [x, y] = pixel;
      depthCtx.strokeStyle = '#fff'; depthCtx.fillStyle = '#fff'; depthCtx.lineWidth = 2*unit;
      depthCtx.beginPath(); depthCtx.arc(x, y, 6*unit, 0, Math.PI*2);
      depthCtx.moveTo(x-12*unit, y); depthCtx.lineTo(x+12*unit, y);
      depthCtx.moveTo(x, y-12*unit); depthCtx.lineTo(x, y+12*unit); depthCtx.stroke();
      depthCtx.fillText(`P${index+1}${cloudMode() ? (state.result.success ? ' 参考点' : ' 候选参考点') : ''}`, x+14*unit, y-10*unit);
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
      ctx.fillStyle = colors[index]; ctx.font = `${14*unit}px sans-serif`;
      ctx.fillText(`ROI${index+1}`, r.x+4*unit, r.y+16*unit);
      if (index === state.selected) ctx.fillRect(r.x+r.width-5*unit, r.y+r.height-5*unit, 10*unit, 10*unit);
    });
    state.result?.lines?.forEach((line, index) => {
      ctx.fillStyle = colors[index]; ctx.strokeStyle = colors[index]; ctx.lineWidth = 2*unit;
      line.edge_points.forEach(([x, y]) => {ctx.beginPath(); ctx.arc(x, y, 2*unit, 0, Math.PI*2); ctx.fill();});
      const [a, b, c] = line.line_abc, [x0, y0, x1, y1] = line.roi;
      ctx.beginPath();
      if (Math.abs(b) > Math.abs(a)) {ctx.moveTo(x0, (-a*x0-c)/b); ctx.lineTo(x1, (-a*x1-c)/b);}
      else {ctx.moveTo((-b*y0-c)/a, y0); ctx.lineTo((-b*y1-c)/a, y1);}
      ctx.stroke();
    });
    state.result?.pixels?.forEach((pixel, index) => {
      if (!pixel?.every(Number.isFinite)) return;
      const [x, y] = pixel;
      ctx.strokeStyle = '#ff3030'; ctx.lineWidth = 2*unit; ctx.beginPath();
      ctx.moveTo(x-12*unit,y); ctx.lineTo(x+12*unit,y); ctx.moveTo(x,y-12*unit); ctx.lineTo(x,y+12*unit); ctx.stroke();
      ctx.font = `${14*unit}px sans-serif`;
      ctx.fillStyle = '#ff3030'; ctx.fillText(`P${index+1}${cloudMode() ? (state.result.success ? ' 参考点' : ' 候选参考点') : ''} (${x.toFixed(2)}, ${y.toFixed(2)})`,x+15*unit,y);
    });
    state.result?.points?.forEach(p => {
      const projected = p.consistency?.projected_edge;
      if (!projected?.length) return;
      ctx.strokeStyle = '#ff8c00'; ctx.lineWidth = 2*unit; ctx.setLineDash([7*unit,4*unit]); ctx.beginPath();
      projected.forEach(([x,y],i) => i ? ctx.lineTo(x,y) : ctx.moveTo(x,y)); ctx.stroke(); ctx.setLineDash([]);
    });
  }
  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return {x: Math.max(0, Math.min(canvas.width, (event.clientX-rect.left)*canvas.width/rect.width)),
            y: Math.max(0, Math.min(canvas.height, (event.clientY-rect.top)*canvas.height/rect.height))};
  }
  $('dp-mode').addEventListener('change', () => {
    $('rack-workbench').dataset.mode = $('dp-mode').value;
    window.dispatchEvent(new Event('resize'));
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
      box.expectedPosition += (original.imageDirection ? original.imageDirection === 'vertical' : state.selected%2) ? box.x-original.x : box.y-original.y;
    } else if (mode === 'resize') {
      box = {...original, width: Math.max(3, p.x-original.x), height: Math.max(3, p.y-original.y)};
    } else {
      const first = state.config.rois.find(r => r.target === targets[state.selected-state.selected%2]);
      const horizontal = original?.imageDirection ? original.imageDirection === 'horizontal'
        : state.selected%2 && first?.imageDirection ? first.imageDirection !== 'horizontal'
        : state.selected%2 === 0;
      box = {...(original || {}), id: `roi${state.selected+1}`, target: targets[state.selected],
             x: Math.min(p.x,start.x), y: Math.min(p.y,start.y), width: Math.abs(p.x-start.x), height: Math.abs(p.y-start.y)};
      box = {edgePolarity:'dark_to_light', edgeMode:'single', edgeSide: horizontal ? 'upper' : 'left',
             gradientThreshold: 10, caliperCount: 20, caliperWidth: 3, expectedSlope: 0, expectedWidth: 20, widthTolerance: 5, ...box};
      box.expectedPosition = horizontal ? box.y+box.height/2 : box.x+box.width/2;
      box.edgeSelection = 'auto';
      box.searchHalfWidth = Math.max(1, (horizontal ? box.height : box.width)/2-2);
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
  $('dp-localization-mode').addEventListener('change', () => action(async () => {
    invalidateFrame();
    if (currentFrame()?.pointcloud_token) await loadFrame();
    else status('请选择配方并采集或导入点云。');
  }));
  $('dp-algorithm').addEventListener('change', () => {
    selectedAlgorithm = $('dp-algorithm').value;
    if (state.config) {state.config.algorithm = $('dp-algorithm').value; edited();}
  });
  async function action(fn) {
    if (state.busy) return;
    state.busy = true; refresh();
    try {await fn();} catch (error) {
      state.result = {success: false, stage: error.stage, errorCode: error.code, errorMessage: error.message};
      state.evaluation = {result: state.result}; state.teachToken = null; state.reference = null;
      draw(); status(error.message);
    }
    finally {state.busy = false; refresh(); renderResults();}
  }
  async function loadFrame() {
    saveFeedback = '';
    const snapshot = currentFrame(), selectedRecipe = recipeId();
    if (!snapshot?.pointcloud_token) throw new Error('请先点击「采集点云」。');
    status('正在读取相机原图和已保存的四 ROI…');
    const data = await request(panel.dataset.prepareUrl, {...snapshot, recipe_id: selectedRecipe, localization_mode: $('dp-localization-mode').value});
    const img = new Image(); img.src = data.image_url; await img.decode();
    if (selectedRecipe !== recipeId() || snapshot.pointcloud_token !== currentFrame()?.pointcloud_token) throw new Error('加载期间配方或采集帧变化，请重新载入。');
    state.dirty = false; state.redraw = false;
    state.image = img; state.config = data.config; state.result = null; state.evaluation = null; state.teachToken = null; state.reference = data.reference;
    state.prepared = {image_token: data.image_token, cloud_token: data.cloud_token, recipe_id: selectedRecipe, frame: snapshot.pointcloud_token};
    canvas.width = data.width; canvas.height = data.height; canvas.hidden = false; canvas.style.display = 'block';
    $('dp-empty').hidden = true;
    if (JSON.stringify(state.config.imageSize) !== JSON.stringify([data.width, data.height])) {
      state.config.rois = []; state.config.imageSize = [data.width, data.height];
      state.config.intersectionBounds = {P1:[0,0,data.width-1,data.height-1], P2:[0,0,data.width-1,data.height-1]};
      status('原图尺寸与已存 ROI 不同，已清除本地框选，请重新绘制后保存。');
    } else status(`原图 ${data.width} × ${data.height}，配方 #${selectedRecipe || '未选择'}。四 ROI 已载入 ${state.config.rois.length}/4。\n${data.three_d_status}`);
    state.config.algorithm = selectedAlgorithm || state.config.algorithm;
    $('dp-algorithm').value = state.config.algorithm;
    state.revision++; refresh(); draw();
    void loadDepth(data, state.prepared);
  }
  $('dp-save-recipe').addEventListener('click', () => action(async () => {
    try {
      if (!recipeId()) throw new Error('请先选择配方。');
      if (!state.prepared || !state.config) throw new Error('请先采集或加载点云，再框选 ROI。');
      checkFrame();
      const selectedRecipe = recipeId(), revision = state.revision;
      const missing = targets.filter(target => !state.config.rois.some(r => r.target === target));
      if (missing.length) throw new Error(`尚缺 ${missing.map(target => labels[targets.indexOf(target)]).join('、')}，请完成后保存。`);
      if (state.drag) throw new Error('请先松开鼠标，结束框选。');
      saveFeedback = '正在保存…'; refresh();
      const saved = await request(panel.dataset.saveUrl, {...state.prepared, recipe_id: selectedRecipe, config: state.config, localization_mode: $('dp-localization-mode').value});
      checkFrame();
      if (revision !== state.revision) throw new Error('保存期间草稿发生变化，请重新保存。');
      state.config = saved.config || state.config;
      state.dirty = false; state.redraw = false;
      const name = $('recipe-select')?.selectedOptions?.[0]?.textContent.trim() || selectedRecipe;
      saveFeedback = '已保存到配方';
      status(`四 ROI 已保存到配方「${name}」。${cloudMode() ? '框选配置已保存；点云标准模板需另点「保存当前帧为点云标准模板」。' : ''}`);
    } catch (error) {
      saveFeedback = `保存失败：${error.message}`;
      status(saveFeedback);
    }
  }));
  $('dp-auto-rois').addEventListener('click', () => action(async () => {
    checkFrame();
    const revision = state.revision;
    status('正在根据当前原图匹配目标边缘并生成四 ROI…');
    const data = await request(panel.dataset.autoRoisUrl, {...state.prepared, recipe_id: recipeId(), config: state.config});
    checkFrame(); if (revision !== state.revision) throw new Error('配置变化，请重新自动框选。');
    state.config = data.config; state.redraw = false;
    $('dp-algorithm').value = state.config.algorithm;
    edited();
    state.result = data.result;
    draw(); renderResults();
    status('已自动生成四 ROI，并通过二维边缘与外推检查。请检查框选位置，点击「开始计算」验证三维；点击「保存配方」保存。');
  }));
  $('dp-evaluate').addEventListener('click', () => action(async () => {
    if (!state.prepared || state.prepared.recipe_id !== recipeId() || state.prepared.frame !== currentFrame()?.pointcloud_token) await loadFrame();
    checkFrame(); state.result = null; state.evaluation = null; state.teachToken = null; state.reference = null; draw(); renderResults();
    status(cloudMode() ? '正在进行点云多尺度 ICP 匹配…' : '正在计算 P1、P2 相机坐标…');
    const revision = state.revision;
    const data = await request(cloudMode() ? panel.dataset.cloudMatchUrl : panel.dataset.evaluateUrl, {...currentFrame(), ...state.prepared, config: state.config, coordinate_system: 'camera'});
    checkFrame(); if (revision !== state.revision) throw new Error('配置变化，请重新校验。');
    state.result = data.result; state.evaluation = data; state.teachToken = data.teach_token; state.reference = data.reference;
    draw();
    status(cloudMode() && data.result.registration
      ? data.result.success ? '匹配通过，坐标与偏差见右侧。'
        : `匹配未通过：${(data.result.registration.failure_reasons || ['请展开匹配详情检查']).join('；')}。当前仅显示候选位置。`
      : data.result.success ? ['相机坐标已计算，右侧显示与标准模板的差值。', ...(data.result.warnings || [])].join('\n') : `${data.result.errorCode}：${data.result.errorMessage}`);

  }));
  $('dp-save-standard').addEventListener('click', () => action(async () => {
    checkFrame();
    const selectedRecipe = recipeId(), revision = state.revision;
    const data = cloudMode()
      ? await request(panel.dataset.cloudMatchUrl, {...currentFrame(), ...state.prepared, recipe_id: selectedRecipe, config: state.config, action: 'save_template'})
      : await request(panel.dataset.teachUrl, {recipe_id: selectedRecipe, teach_token: state.teachToken});
    if (cloudMode()) {state.result = data.result; state.evaluation = data;}
    checkFrame();
    if (revision !== state.revision || selectedRecipe !== recipeId()) return;
    state.reference = data.reference;
    if (state.evaluation) state.evaluation.robot_result = data.robot_result;
    state.config = data.config || state.config;
    state.dirty = false;
    state.teachToken = null;
    draw();
    const name = $('recipe-select')?.selectedOptions?.[0]?.textContent.trim() || selectedRecipe;
    status(cloudMode() ? `点云标准模板已保存到配方「${name}」。请加载待测帧后开始计算。` : `P1、P2 相机坐标已保存为配方「${name}」的标准模板。`);
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
  $('recipe-select')?.addEventListener('change', invalidateFrame);
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
        roi_config: {...snapshot.roi_config, ...(current && state.config ? {dual_point:state.config} : {})}};
    };
    bridge.load = payload => {
      originalLoad(payload); invalidateFrame();
      $('dp-frame-status').textContent = '数据包已加载，正在自动载入原图与四 ROI…';
      // 等待点云图片加载完成后自动触发「载入原图与四 ROI」，省去手动点击
      const img = document.getElementById('rl-depth-image');
      const trigger = () => action(loadFrame);
      if (img && (!img.complete || !img.naturalWidth)) {
        img.addEventListener('load', trigger, { once: true });
      } else {
        // 图片已就绪（缓存命中），稍延迟确保 invalidateFrame 完成
        setTimeout(trigger, 0);
      }
    };
  }
  window.addEventListener('resize', draw);
  refresh(); renderResults();
})();
