/* ============================================================
 *  3D 料架定位工作台 · 交互逻辑
 *  采集点云 → 画 ROI → 计算偏差 → 保存到数据库
 *  次级：按 POS/层号自动拍照计算 + 历史记录
 * ============================================================ */
(function () {
  const CFG = window.rackLocatorConfig || {};
  const $ = (id) => document.getElementById(id);
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

  // ── 配置完整性校验 ──────────────────────────────────────
  if (!window.rackLocatorConfig || !CFG.captureUrl) {
    console.error('[rack_locator_workbench] rackLocatorConfig 未定义或 captureUrl 缺失！请检查模板中的 <script> 是否有语法错误。');
  }

  // ── 工作台状态 ──────────────────────────────────────────
  const state = {
    token: null,         // 持久化点云 token
    roi: null,           // 真实图像像素 ROI {x,y,w,h}
    drawing: false,
    start: null,
    displayRoi: null,
    lastResultId: null,
    lastResultOk: false,
    currentRecipe: null,
    pendingRoi: null,    // 待应用的 ROI（在采集点云前加载）
  };

  // ── 暴露设置 ROI 的接口供外部调用 ────────────────────────
  window.rackLocatorSetRoi = function(targetRoi) {
    if (!targetRoi) return;
    
    // 如果已经有点云图像，立即应用
    if (state.token && image.style.display !== 'none') {
      state.roi = {
        x: targetRoi.x,
        y: targetRoi.y,
        w: targetRoi.w,
        h: targetRoi.h,
        feature_type: targetRoi.feature_type || 'rack_reference'
      };
      
      // 转换为显示坐标
      const nat = naturalDims();
      const scaleX = canvas.width / nat.w;
      const scaleY = canvas.height / nat.h;
      state.displayRoi = {
        x: state.roi.x * scaleX,
        y: state.roi.y * scaleY,
        w: state.roi.w * scaleX,
        h: state.roi.h * scaleY,
      };
      
      draw();
      setReadout();
      setStatus('已加载配方 ROI，可直接点击「计算偏差」。');
      console.log('ROI 已应用到画布');
      syncRoiToRightSide();
    } else {
      // 如果还没有点云，保存到待应用状态
      state.pendingRoi = targetRoi;
      console.log('ROI 已保存，等待点云采集后应用');
    }
  };

  // ── 同步 ROI 到右侧结果图 ──────────────────────────────
  function syncRoiToRightSide() {
    const rightImg = $('rl-result-img');
    const ph = $('rl-result-ph');
    if (!image || !image.src || !state.roi) return;
    
    try {
      const tmpCanvas = document.createElement('canvas');
      const nat = naturalDims();
      tmpCanvas.width = nat.w;
      tmpCanvas.height = nat.h;
      const tCtx = tmpCanvas.getContext('2d');
      
      tCtx.drawImage(image, 0, 0, tmpCanvas.width, tmpCanvas.height);
      
      const r = state.roi;
      tCtx.strokeStyle = '#22c55e';
      tCtx.lineWidth = Math.max(3, tmpCanvas.width / 200);
      tCtx.setLineDash([8, 4]);
      tCtx.strokeRect(r.x, r.y, r.w, r.h);
      
      tCtx.fillStyle = 'rgba(34,197,94,0.16)';
      tCtx.fillRect(r.x, r.y, r.w, r.h);
      
      tCtx.fillStyle = '#22c55e';
      tCtx.font = `${Math.max(14, tmpCanvas.width / 40)}px sans-serif`;
      tCtx.fillText('target ROI', r.x + 8, Math.max(18, r.y + 18));
      
      rightImg.src = tmpCanvas.toDataURL('image/jpeg', 0.9);
      rightImg.style.display = 'block';
      if (ph) ph.style.display = 'none';
    } catch (e) {
      console.error('同步 ROI 到右侧失败', e);
    }
  }


  // ── Loading 遮罩 ─────────────────────────────────────────
  function showLoading(msg) {
    if ($('rl-loading')) return;
    const el = document.createElement('div');
    el.id = 'rl-loading';
    el.innerHTML = `<div class="rl-loading-card"><div class="rl-spinner"></div><p>${msg || '处理中...'}</p></div>`;
    document.body.appendChild(el);
  }
  function hideLoading() { $('rl-loading')?.remove(); }

  async function postJson(url, body) {
    if (!url || typeof url !== 'string' || !url.startsWith('/')) {
      throw new Error(`API URL 未正确配置 (值为: ${url})。请刷新页面重试，或检查浏览器控制台是否有JS语法错误。`);
    }
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify(body || {}),
    });
    
    // 检查响应的Content-Type
    const contentType = res.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      // 如果不是JSON响应，读取文本内容用于调试
      const text = await res.text();
      console.error('服务器返回非JSON响应:', {
        status: res.status,
        statusText: res.statusText,
        contentType: contentType,
        responseText: text.substring(0, 500) // 只记录前500字符
      });
      
      // 如果是4xx或5xx错误，提供更有用的错误信息
      if (!res.ok) {
        throw new Error(`服务器错误 (${res.status}): ${res.statusText}。可能是URL路径错误或权限问题。`);
      }
      
      throw new Error('服务器返回了HTML页面而不是JSON数据。请检查API URL配置是否正确。');
    }
    
    // 正常解析JSON
    return res.json();
  }

  function setStatus(text) { const n = $('rl-status'); if (n) n.textContent = text; }

  function apiPayload(data) {
    if (!data || !data.data) return data || {};
    if (typeof data.data === 'object' && !Array.isArray(data.data)) {
      return {
        success: data.success,
        error: data.error || '',
        ...data.data,
      };
    }
    return {
      success: data.success,
      error: data.error || '',
      data: data.data,
    };
  }

  function numberInput(id, fallback) {
    const node = $(id);
    const value = node ? Number(node.value) : NaN;
    return Number.isFinite(value) ? value : fallback;
  }

  function currentRackSide() {
    return $('rack-side')?.value || 'LEFT';
  }

  function currentLayerNo() {
    return numberInput('layer-no-select', numberInput('layer-no', 1));
  }

  function currentMode() {
    return $('locate-mode')?.value || 'local';
  }

  function currentLocateType() {
    const typeControl = $('locate-type');
    if (typeControl) {
      return typeControl.value || 'LAYER';
    }
    return String(currentMode()).toLowerCase() === 'global' ? 'GLOBAL' : 'LAYER';
  }

  function currentLayerIndex() {
    const indexControl = $('layer-index');
    if (indexControl) {
      return Number(indexControl.value) || 1;
    }
    return currentLocateType() === 'GLOBAL' ? 0 : currentLayerNo();
  }

  // 同步新旧控件
  function syncControls() {
    const locateType = currentLocateType();
    const layerIndex = currentLayerIndex();
    
    // 同步到旧控件
    if ($('locate-mode')) {
      $('locate-mode').value = locateType === 'GLOBAL' ? 'global' : 'local';
    }
    if ($('layer-no')) {
      $('layer-no').value = layerIndex;
    }
    if ($('layer-no-select')) {
      $('layer-no-select').value = layerIndex;
    }
    
    // 同步到新控件
    if ($('locate-type')) {
      $('locate-type').value = locateType;
    }
    if ($('layer-index')) {
      $('layer-index').value = layerIndex;
    }
  }

  function semanticPayload(extra) {
    return {
      locate_type: currentLocateType(),
      layer_index: currentLayerIndex(),
      layer_no: currentLayerIndex(),
      ...(extra || {}),
    };
  }

  function setButton(id, enabled) {
    const node = $(id);
    if (node) node.disabled = !enabled;
  }

  function refreshActionState() {
    // 简化版：只控制三个主要按钮
    setButton('btn-capture', true);  // 采集点云始终可用
    setButton('btn-redraw', Boolean(state.token));  // 有点云后可以重画ROI
    setButton('btn-calculate', Boolean(state.token));  // 有点云后可以计算
  }

  async function refreshCurrentRecipe() {
    if (!CFG.currentRecipeUrl) return;
    try {
      const query = new URLSearchParams({
        locate_type: currentLocateType(),
        layer_index: String(currentLayerIndex()),
      });
      const res = await fetch(`${CFG.currentRecipeUrl}?${query.toString()}`);
      const data = apiPayload(await res.json());
      const recipe = data.recipe || null;
      state.currentRecipe = recipe;
      if (recipe && recipe.id && $('recipe-id')) {
        $('recipe-id').value = recipe.id;
      }
    } catch (e) {
      state.currentRecipe = null;
    }
  }

  function currentRoi3D() {
    return {
      x_min: numberInput('roi-x-min', -100),
      x_max: numberInput('roi-x-max', 100),
      y_min: numberInput('roi-y-min', -100),
      y_max: numberInput('roi-y-max', 100),
      z_min: numberInput('roi-z-min', -100),
      z_max: numberInput('roi-z-max', 100),
    };
  }

  // ── 选中配方的参数（标准坐标） ───────────
  // 新方案：配方选择改为卡片点击，数据存放在 .rl-recipe-card.selected 的 dataset 上
  function selectedCardData() {
    const card = document.querySelector('.rl-recipe-card.selected');
    return card ? card.dataset : null;
  }
  function currentRecipeData() {
    // 优先从下拉框读取（新版 UI）
    const select = document.getElementById('recipe-select');
    if (select && select.selectedIndex >= 0) {
      const option = select.options[select.selectedIndex];
      if (option && option.value) {
        return {
          standard_x: Number(option.dataset.sx || 0),
          standard_y: Number(option.dataset.sy || 0),
          standard_z: Number(option.dataset.sz || 0),
          layer_no: Number(option.dataset.layer || 1),
          position_no: Number(option.dataset.pos || 1),
          locate_type: currentLocateType(),
          layer_index: currentLayerIndex()
        };
      }
    }

    // 回退到旧的卡片读取方式
    const d = selectedCardData();
    const data = { layer_no: currentLayerIndex(), locate_type: currentLocateType(), layer_index: currentLayerIndex() };
    if (d) {
      data.standard_x = Number(d.sx || 0);
      data.standard_y = Number(d.sy || 0);
      data.standard_z = Number(d.sz || 0);
    }
    return data;
  }

  // ── 画布 / ROI ───────────────────────────────────────────
  const image = $('rl-depth-image');
  const canvas = $('rl-canvas');
  const ctx = canvas.getContext('2d');

  function resizeCanvas() {
    const rect = image.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(rect.width));
    canvas.height = Math.max(1, Math.round(rect.height));
    draw();
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const roi = state.displayRoi;
    if (!roi) return;
    ctx.save();
    ctx.strokeStyle = '#22c55e';
    ctx.lineWidth = 3;
    ctx.setLineDash([8, 4]);
    ctx.strokeRect(roi.x, roi.y, roi.w, roi.h);
    ctx.fillStyle = 'rgba(34,197,94,0.16)';
    ctx.fillRect(roi.x, roi.y, roi.w, roi.h);
    ctx.fillStyle = '#22c55e';
    ctx.font = '14px sans-serif';
    ctx.fillText('target ROI', roi.x + 8, Math.max(18, roi.y + 18));
    ctx.restore();
  }

  function pointerToCanvas(e) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(canvas.width, e.clientX - rect.left)),
      y: Math.max(0, Math.min(canvas.height, e.clientY - rect.top)),
    };
  }
  function naturalDims() {
    return {
      w: image.naturalWidth || Number(image.dataset.naturalWidth) || canvas.width,
      h: image.naturalHeight || Number(image.dataset.naturalHeight) || canvas.height,
    };
  }
  function displayToReal(d) {
    const n = naturalDims();
    const sx = n.w / canvas.width, sy = n.h / canvas.height;
    return { x: Math.round(d.x * sx), y: Math.round(d.y * sy), w: Math.round(d.w * sx), h: Math.round(d.h * sy) };
  }
  function setReadout() {
    const n = $('rl-roi-readout');
    if (!n) return;
    if (!state.roi) { n.textContent = '拖拽绘制 ROI'; return; }
    const r = state.roi;
    n.textContent = `ROI  x=${r.x}  y=${r.y}  w=${r.w}  h=${r.h}`;
  }

  canvas.addEventListener('mousedown', (e) => {
    if (!state.token) return;
    state.drawing = true;
    state.start = pointerToCanvas(e);
    state.displayRoi = { x: state.start.x, y: state.start.y, w: 0, h: 0 };
    draw();
  });
  canvas.addEventListener('mousemove', (e) => {
    if (!state.drawing || !state.start) return;
    const c = pointerToCanvas(e);
    state.displayRoi = {
      x: Math.min(state.start.x, c.x), y: Math.min(state.start.y, c.y),
      w: Math.abs(c.x - state.start.x), h: Math.abs(c.y - state.start.y),
    };
    draw();
  });
  window.addEventListener('mouseup', () => {
    if (!state.drawing || !state.displayRoi) return;
    state.drawing = false;
    state.start = null;
    if (state.displayRoi.w < 3 || state.displayRoi.h < 3) { state.displayRoi = null; draw(); return; }
    const real = displayToReal(state.displayRoi);
    state.roi = { x: real.x, y: real.y, w: real.w, h: real.h, feature_type: 'rack_reference' };
    setReadout();
    setStatus('ROI 已绘制，可点击「计算偏差」。');
    syncRoiToRightSide();
  });

  // ── 采集点云 ─────────────────────────────────────────────
  $('btn-capture').addEventListener('click', async () => {
    showLoading('3D 相机采集中...');
    try {
      // 优先使用工作台专用端点
      const captureApiUrl = CFG.captureUrl || CFG.legacyCaptureUrl || '/vision/api/rack-location/workbench/capture/';
      console.log('[采集点云] 使用API端点:', captureApiUrl);
      
      const raw = await postJson(captureApiUrl, semanticPayload({
        recipe_id: $('recipe-id').value || null,
        rack_side: currentRackSide(),
      }));
      const data = apiPayload(raw);
      if (!data.success) { setStatus(data.error || '采集失败'); return; }
      state.token = data.pointcloud_token;
      state.alignmentToken = null;
      state.lastResultId = null;
      state.lastResultOk = false;
      state.roi = null; state.displayRoi = null;
      const previewUrl = data.pointcloud_preview_url || data.preview_image_url;
      if (previewUrl) {
        const urlWithTime = previewUrl + '?t=' + Date.now();
        image.src = urlWithTime;
        // 同步显示到右侧结果区
        $('rl-result-img').src = urlWithTime;
        $('rl-result-img').style.display = 'block';
        if ($('rl-result-ph')) $('rl-result-ph').style.display = 'none';
      }
      image.dataset.naturalWidth = data.image_width;
      image.dataset.naturalHeight = data.image_height;
      image.style.display = 'block';
      canvas.style.display = 'block';
      $('rl-placeholder').style.display = 'none';
      $('rl-roi-readout').style.display = 'block';
      $('rl-source').textContent = '数据源 ' + (data.source || '—');
      setReadout();
      
      // 如果有待应用的 ROI，在点云加载后自动应用
      if (state.pendingRoi || window.tempPendingRoi) {
        const pendingRoi = state.pendingRoi || window.tempPendingRoi;
        // 等待图像加载完成
        image.onload = function() {
          resizeCanvas();
          window.rackLocatorSetRoi(pendingRoi);
          state.pendingRoi = null; // 清除待应用状态
          window.tempPendingRoi = null;
        };
      }
      
      if (data.source && data.source.indexOf('sample') === 0) {
        setStatus('⚠ 未取到真实相机数据，已回退模拟点云'
          + (data.fallback_reason ? '：' + data.fallback_reason : '（相机未连接）')
          + '。请检查相机连接后重试。');
      } else {
        setStatus(state.pendingRoi ? '点云已采集，配方 ROI 已自动显示。' : '点云已采集（真实相机），请在图上拖拽绘制 ROI。');
      }
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); refreshActionState(); }
  });

  $('btn-redraw').addEventListener('click', () => {
    state.roi = null; state.displayRoi = null;
    state.alignmentToken = null;
    draw(); setReadout();
    setStatus('请重新拖拽绘制 ROI。');
    refreshActionState();
  });

  // ── 计算偏差 ─────────────────────────────────────────────
  $('btn-calculate').addEventListener('click', async () => {
    if (!state.token) { setStatus('请先采集点云。'); return; }
    showLoading('计算坐标偏差中...');
    try {
      // 优先使用工作台专用端点
      const calculateApiUrl = CFG.calculateUrl || CFG.legacyCalculateUrl || CFG.testLocateUrl || '/vision/api/rack-location/workbench/calculate/';
      console.log('[计算偏差] 使用API端点:', calculateApiUrl);
      
      const raw = await postJson(calculateApiUrl, semanticPayload({
        pointcloud_token: state.token,
        roi: currentRoi3D(),
        roi_config: { target_roi: state.roi },
        rack_side: currentRackSide(),
        recipe_id: $('recipe-id').value || null,
        recipe_data: currentRecipeData(),
      }));
      const data = apiPayload(raw);
      if (!data.success) { setStatus(data.error || '计算失败'); return; }
      renderResult(data.result);
      $('btn-save').disabled = false;
      $('last-time').textContent = '上次计算：' + new Date().toLocaleString('zh-CN', { hour12: false });
      setStatus(data.result.locate_ok ? '计算完成：定位 OK。' : ('计算完成：定位 NG · ' + (data.result.error_message || data.result.error_code || '')));
      
      // 计算完成后自动选中下一个配方
      selectNextRecipe();
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); }
  });
  
  // ── 自动选中下一个配方 ──────────────────────────────────
  function selectNextRecipe() {
    const select = document.getElementById('recipe-select');
    if (!select || select.options.length === 0) return;
    
    const currentIndex = select.selectedIndex;
    let nextIndex = currentIndex + 1;
    
    // 如果已经是最后一个，循环回到第一个
    if (nextIndex >= select.options.length) {
      nextIndex = 0;
    }
    
    // 跳过空选项（如果有的话）
    while (nextIndex < select.options.length && !select.options[nextIndex].value) {
      nextIndex++;
      if (nextIndex >= select.options.length) {
        nextIndex = 0;
        break;
      }
    }
    
    // 更新下拉框选择
    if (select.options[nextIndex] && select.options[nextIndex].value) {
      select.selectedIndex = nextIndex;
      // 触发change事件以应用配方
      select.dispatchEvent(new Event('change'));
      
      console.log(`已自动选中下一个配方：${select.options[nextIndex].text}`);
    }
  }

  // ── 保存结果到数据库 ─────────────────────────────────────
  // 移除保存功能，简化工作台为纯计算预览工具

  // ── 移除不需要的高级功能 ──────────────────────────────────
  // 移除：自动对齐、保存ROI、写入PLC、自动触发、历史记录等复杂功能

  // ── 渲染结果 ─────────────────────────────────────────────
  function renderResult(r) {
    const ok = r.locate_ok ?? r.is_success;
    const v = $('rl-verdict');
    v.className = 'rl-verdict ' + (ok ? 'ok' : 'fail');
    $('rl-verdict-icon').textContent = ok ? '✅' : '❌';
    $('rl-verdict-text').textContent = ok ? '定位 OK' : '定位 NG · 请核查';
    $('rl-verdict-sub').textContent = ok ? '计算完成' : (r.error_message || r.error_code || '计算异常');

    setOffset('x', r.final_offset_x ?? r.offset_x, null);
    setOffset('y', r.final_offset_y ?? r.offset_y, null);
    setOffset('z', r.final_offset_z ?? r.offset_z, null);
    setOffset('rz', r.final_offset_rz ?? r.offset_rz, null);

    const conf = Number(r.confidence || 0);
    const bar = $('conf-bar'), lab = $('conf-val');
    bar.style.width = Math.min(100, conf * 100) + '%';
    bar.className = 'rl-conf-fill ' + (conf >= 0.8 ? 'high' : conf >= 0.7 ? 'mid' : 'low');
    lab.textContent = (conf * 100).toFixed(1) + '%';

    if (r.result_image_url) {
      $('rl-result-img').src = r.result_image_url + '?t=' + Date.now();
      $('rl-result-img').style.display = 'block';
      $('rl-result-ph').style.display = 'none';
    }

    const meta = r.result_data || {};
    const actX = Number(r.actual_x || 0);
    const actY = Number(r.actual_y || 0);
    const actZ = Number(r.actual_z || 0);
    
    // 更新标准值（从当前选中的配方中获取）
    const recipeData = currentRecipeData();
    if ($('d-sx')) $('d-sx').textContent = (recipeData.standard_x || 0).toFixed(2);
    if ($('d-sy')) $('d-sy').textContent = (recipeData.standard_y || 0).toFixed(2);
    if ($('d-sz')) $('d-sz').textContent = (recipeData.standard_z || 0).toFixed(2);

    // 更新实测值
    if ($('d-ax')) $('d-ax').textContent = actX.toFixed(2);
    if ($('d-ay')) $('d-ay').textContent = actY.toFixed(2);
    if ($('d-az')) $('d-az').textContent = actZ.toFixed(2);


    $('d-points').textContent = meta.valid_point_count ?? meta.point_count ?? '—';

    $('rl-detail').style.display = 'flex';
    refreshActionState();
  }


  function setOffset(axis, val, limit) {
    const cell = $('cell-' + axis), el = $('off-' + axis);
    const num = parseFloat(val);
    el.textContent = isNaN(num) ? '—' : (num > 0 ? '+' : '') + num.toFixed(2);
    cell.classList.remove('positive', 'negative', 'zero', 'out');
    if (isNaN(num)) return;
    if (limit != null && Math.abs(num) > limit) cell.classList.add('out');
    else if (Math.abs(num) < 0.01) cell.classList.add('zero');
    else if (num > 0) cell.classList.add('positive');
    else cell.classList.add('negative');
  }


  window.addEventListener('resize', resizeCanvas);
  image.addEventListener('load', resizeCanvas);
  
  // 监听新旧控件变化并同步
  ['locate-mode', 'layer-no-select', 'layer-no', 'locate-type', 'layer-index'].forEach((id) => {
    $(id)?.addEventListener('change', async () => {
      syncControls();
      state.alignmentToken = null;
      state.lastResultId = null;
      state.lastResultOk = false;
      refreshActionState();
      await refreshCurrentRecipe();
    });
  });

  document.addEventListener('DOMContentLoaded', async () => {
    syncControls();
    refreshActionState();
    await refreshCurrentRecipe();
  });
  if (document.readyState !== 'loading') {
    syncControls();
    refreshActionState();
    refreshCurrentRecipe();
  }
}());
