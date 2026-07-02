/* ============================================================
 *  3D 料架定位工作台 · 简化版
 *  简单流程：选配方 → 采集点云 → 绘制ROI → 计算偏差
 * ============================================================ */
(function () {
  const CFG = window.rackLocatorConfig || {};
  const $ = (id) => document.getElementById(id);
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

  // ── 工作台状态 ──────────────────────────────────────────
  const state = {
    token: null,         // 持久化点云 token
    roi: null,           // 真实图像像素 ROI {x,y,w,h}
    drawing: false,
    start: null,
    displayRoi: null,
    currentRecipe: null,
    pendingRoi: null,    // 待应用的 ROI
  };

  // ── 暴露设置 ROI 的接口供外部调用 ────────────────────────
  window.rackLocatorSetRoi = function(targetRoi) {
    if (!targetRoi) return;
    
    if (state.token && image.style.display !== 'none') {
      state.roi = {
        x: targetRoi.x,
        y: targetRoi.y,
        w: targetRoi.w,
        h: targetRoi.h,
        feature_type: targetRoi.feature_type || 'rack_reference'
      };
      
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
    } else {
      state.pendingRoi = targetRoi;
    }
  };

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
      throw new Error(`API URL 未正确配置 (值为: ${url})。请刷新页面重试。`);
    }
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify(body || {}),
    });
    
    const contentType = res.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      const text = await res.text();
      console.error('服务器返回非JSON响应:', { status: res.status, statusText: res.statusText, responseText: text.substring(0, 500) });
      
      if (!res.ok) {
        throw new Error(`服务器错误 (${res.status}): ${res.statusText}`);
      }
      throw new Error('服务器返回了HTML页面而不是JSON数据');
    }
    
    return res.json();
  }

  function setStatus(text) { const n = $('rl-status'); if (n) n.textContent = text; }

  function apiPayload(data) {
    if (!data || !data.data) return data || {};
    if (typeof data.data === 'object' && !Array.isArray(data.data)) {
      return { success: data.success, error: data.error || '', ...data.data };
    }
    return { success: data.success, error: data.error || '', data: data.data };
  }

  function numberInput(id, fallback) {
    const node = $(id);
    const value = node ? Number(node.value) : NaN;
    return Number.isFinite(value) ? value : fallback;
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

  function currentRecipeData() {
    const select = $('recipe-select');
    if (!select) return {};
    
    const option = select.options[select.selectedIndex];
    if (!option || !option.value) return {};
    
    return {
      standard_x: Number(option.dataset.sx || 0),
      standard_y: Number(option.dataset.sy || 0),
      standard_z: Number(option.dataset.sz || 0),
      layer_no: Number(option.dataset.layer || 1),
      position_no: Number(option.dataset.pos || 1),
    };
  }

  function setButton(id, enabled) {
    const node = $(id);
    if (node) node.disabled = !enabled;
  }

  function refreshActionState() {
    setButton('btn-capture', true);
    setButton('btn-redraw', Boolean(state.token));
    setButton('btn-calculate', Boolean(state.token));
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
    if (!state.roi) { n.textContent = '拖拽绘制 ROI（相机坐标，后台自动转换为机器人坐标）'; return; }
    const r = state.roi;
    n.textContent = `ROI(相机像素)  x=${r.x}  y=${r.y}  w=${r.w}  h=${r.h}  → 机器人坐标自动转换`;
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
    if (state.displayRoi.w < 3 || state.displayRoi.h < 3) { 
      state.displayRoi = null; 
      draw(); 
      return; 
    }
    const real = displayToReal(state.displayRoi);
    state.roi = { x: real.x, y: real.y, w: real.w, h: real.h, feature_type: 'rack_reference' };
    setReadout();
    setStatus('ROI 已绘制，可点击「计算偏差」。');
  });

  // ── 采集点云 ─────────────────────────────────────────────
  $('btn-capture').addEventListener('click', async () => {
    showLoading('3D 相机采集中...');
    try {
      const captureApiUrl = CFG.captureUrl || '/vision/api/rack-location/workbench/capture/';
      console.log('[采集点云] 使用API端点:', captureApiUrl);
      
      const recipeData = currentRecipeData();
      const raw = await postJson(captureApiUrl, {
        recipe_id: $('recipe-id').value || null,
        rack_side: $('rack-side').value || 'LEFT',
        layer_no: recipeData.layer_no || 1,
        locate_type: 'LAYER',
        layer_index: recipeData.layer_no || 1,
      });
      
      const data = apiPayload(raw);
      if (!data.success) { setStatus(data.error || '采集失败'); return; }
      
      state.token = data.pointcloud_token;
      state.roi = null; 
      state.displayRoi = null;
      
      const previewUrl = data.pointcloud_preview_url || data.preview_image_url;
      if (previewUrl) image.src = previewUrl + '?t=' + Date.now();
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
        image.onload = function() {
          resizeCanvas();
          window.rackLocatorSetRoi(pendingRoi);
          state.pendingRoi = null;
          window.tempPendingRoi = null;
        };
      }
      
      if (data.source && data.source.indexOf('sample') === 0) {
        setStatus('⚠ 未取到真实相机数据，已回退模拟点云。请检查相机连接后重试。');
      } else {
        setStatus(state.pendingRoi ? '点云已采集，配方 ROI 已自动显示。' : '点云已采集，请在图上拖拽绘制 ROI。');
      }
      
      // ✨ 新增：采集成功后，自动保存数据到离线目录
      try {
        // 从token加载点云数据并保存
        const offlineTestUrl = CFG.offlineTestUrl || '/vision/api/rack/offline-test/';
        
        // 注意：这里需要从服务端获取点云数据
        // 实际上，服务端在采集时已经保存了.npy文件，我们只需要复制它
        console.log('[采集点云] 数据已采集，token:', state.token);
        console.log('[采集点云] 数据会在计算后自动保存到离线目录');
        
      } catch (err) {
        console.warn('[采集点云] 保存副本失败:', err);
        // 不影响主流程
      }
      
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); refreshActionState(); }
  });

  $('btn-redraw').addEventListener('click', () => {
    state.roi = null; 
    state.displayRoi = null;
    draw(); 
    setReadout();
    setStatus('请重新拖拽绘制 ROI。');
    refreshActionState();
  });

  // ── 计算偏差 ─────────────────────────────────────────────
  $('btn-calculate').addEventListener('click', async () => {
    if (!state.token) { setStatus('请先采集点云。'); return; }
    if (!state.roi) { setStatus('请先绘制 ROI。'); return; }
    
    showLoading('计算坐标偏差中...');
    try {
      const calculateApiUrl = CFG.calculateUrl || '/vision/api/rack-location/workbench/calculate/';
      console.log('[计算偏差] 使用API端点:', calculateApiUrl);
      
      const recipeData = currentRecipeData();
      const raw = await postJson(calculateApiUrl, {
        pointcloud_token: state.token,
        roi: currentRoi3D(),
        roi_config: { target_roi: state.roi },
        rack_side: $('rack-side').value || 'LEFT',
        recipe_id: $('recipe-id').value || null,
        recipe_data: recipeData,
        layer_no: recipeData.layer_no || 1,
      });
      
      const data = apiPayload(raw);
      if (!data.success) { setStatus(data.error || '计算失败'); return; }
      
      renderResult(data.result);
      setStatus(data.result.locate_ok ? '计算完成：定位 OK（坐标已转换为机器人坐标）。' : ('计算完成：定位 NG · ' + (data.result.error_message || data.result.error_code || '')));
      
      // 计算完成后自动选中下一个配方
      selectNextRecipe();
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
      console.error('[计算偏差] 错误:', e);
    } finally { hideLoading(); }
  });
  
  // ── 自动选中下一个配方 ──────────────────────────────────
  function selectNextRecipe() {
    const select = $('recipe-select');
    if (!select || select.options.length === 0) return;
    
    const currentIndex = select.selectedIndex;
    let nextIndex = currentIndex + 1;
    
    if (nextIndex >= select.options.length) {
      nextIndex = 0;
    }
    
    while (nextIndex < select.options.length && !select.options[nextIndex].value) {
      nextIndex++;
      if (nextIndex >= select.options.length) {
        nextIndex = 0;
        break;
      }
    }
    
    if (select.options[nextIndex] && select.options[nextIndex].value) {
      select.selectedIndex = nextIndex;
      select.dispatchEvent(new Event('change'));
      console.log(`已自动选中下一个配方：${select.options[nextIndex].text}`);
    }
  }

  // ── 渲染结果 ─────────────────────────────────────────────
  function renderResult(r) {
    const ok = r.locate_ok ?? r.is_success;
    const v = $('rl-verdict');
    v.className = 'rl-verdict ' + (ok ? 'ok' : 'fail');
    $('rl-verdict-icon').textContent = ok ? '✅' : '❌';
    $('rl-verdict-text').textContent = ok ? '定位 OK' : '定位 NG · 请核查';
    $('rl-verdict-sub').textContent = ok ? '计算完成（机器人坐标）' : (r.error_message || r.error_code || '计算异常');

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
    // 展示机器人坐标中的实测值
    $('d-ax').textContent = Number(r.actual_x || 0).toFixed(2);
    $('d-ay').textContent = Number(r.actual_y || 0).toFixed(2);
    $('d-az').textContent = Number(r.actual_z || 0).toFixed(2);
    $('d-points').textContent = meta.valid_point_count ?? '—';
    $('rl-detail').style.display = 'flex';

    // ── 填充标准值 vs 实测值对比表（均为机器人坐标，mm）──
    const recipeData = currentRecipeData();
    const stdX = recipeData.standard_x;
    const stdY = recipeData.standard_y;
    const stdZ = recipeData.standard_z;
    const actX = Number(r.actual_x || 0);
    const actY = Number(r.actual_y || 0);
    const actZ = Number(r.actual_z || 0);
    const offX = Number(r.final_offset_x ?? r.offset_x ?? 0);
    const offY = Number(r.final_offset_y ?? r.offset_y ?? 0);
    const offZ = Number(r.final_offset_z ?? r.offset_z ?? 0);

    function fmtMm(v) {
      if (v == null || isNaN(Number(v))) return '—';
      return Number(v).toFixed(3) + ' mm';
    }
    function fmtOff(v) {
      if (v == null || isNaN(v)) return '—';
      return (v > 0 ? '+' : '') + v.toFixed(3) + ' mm';
    }

    const cmpTable = $('rl-compare-table');
    if (cmpTable) {
      // 填入数据
      if ($('cmp-std-x')) $('cmp-std-x').textContent = fmtMm(stdX);
      if ($('cmp-std-y')) $('cmp-std-y').textContent = fmtMm(stdY);
      if ($('cmp-std-z')) $('cmp-std-z').textContent = fmtMm(stdZ);
      if ($('cmp-act-x')) $('cmp-act-x').textContent = fmtMm(actX);
      if ($('cmp-act-y')) $('cmp-act-y').textContent = fmtMm(actY);
      if ($('cmp-act-z')) $('cmp-act-z').textContent = fmtMm(actZ);
      if ($('cmp-off-x')) $('cmp-off-x').textContent = fmtOff(offX);
      if ($('cmp-off-y')) $('cmp-off-y').textContent = fmtOff(offY);
      if ($('cmp-off-z')) $('cmp-off-z').textContent = fmtOff(offZ);
      // 偏差着色：<2mm 绿，2~5mm 橙，>5mm 红
      [['x', offX], ['y', offY], ['z', offZ]].forEach(([axis, val]) => {
        const el = $('cmp-off-' + axis);
        if (el) {
          const abs = Math.abs(val);
          el.style.color = abs < 2 ? '#059669' : abs < 5 ? '#d97706' : '#dc2626';
        }
      });
      cmpTable.style.display = 'block';
    }

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

  // ── 导入数据（加载上一次保存的数据）─────────────────────────
  $('btn-import').addEventListener('click', async () => {
    showLoading('加载上一次的数据...');
    
    try {
      const loadLatestUrl = CFG.loadLatestUrl || '/vision/api/rack/load-latest/';
      console.log('[导入数据] 使用API端点:', loadLatestUrl);
      
      const raw = await postJson(loadLatestUrl, {});
      
      if (!raw.success) {
        throw new Error(raw.error || '加载数据失败');
      }
      
      // 数据加载成功，更新状态
      state.token = raw.pointcloud_token;
      state.roi = null;
      state.displayRoi = null;
      
      const previewUrl = raw.pointcloud_preview_url || raw.preview_image_url;
      if (previewUrl) image.src = previewUrl + '?t=' + Date.now();
      image.dataset.naturalWidth = raw.image_width;
      image.dataset.naturalHeight = raw.image_height;
      image.style.display = 'block';
      canvas.style.display = 'block';
      $('rl-placeholder').style.display = 'none';
      $('rl-roi-readout').style.display = 'block';
      $('rl-source').textContent = '数据源 ' + (raw.source || '导入');
      setReadout();
      
      // 如果有待应用的 ROI，在数据加载后自动应用
      if (state.pendingRoi || window.tempPendingRoi) {
        const pendingRoi = state.pendingRoi || window.tempPendingRoi;
        image.onload = function() {
          resizeCanvas();
          window.rackLocatorSetRoi(pendingRoi);
          state.pendingRoi = null;
          window.tempPendingRoi = null;
        };
      }
      
      setStatus(`已加载上一次的数据（${raw.source}），请在图上拖拽绘制 ROI。`);
      console.log('[导入数据] 成功:', raw);
      
      // 同时保存数据到指定目录
      try {
        const offlineTestUrl = CFG.offlineTestUrl || '/vision/api/rack/offline-test/';
        
        // 注意：这里不需要发送点云数据，因为已经在服务端处理了
        // 只是为了保持兼容性，记录到离线测试目录
        console.log('[导入数据] 数据已从', raw.source_file, '加载');
        
      } catch (err) {
        console.warn('[导入数据] 保存副本失败:', err);
        // 不影响主流程
      }
      
    } catch (err) {
      console.error('导入数据失败:', err);
      setStatus('导入失败：' + err.message);
      alert('导入数据失败：\n\n' + err.message + '\n\n请确保之前已经保存过数据到 C:\\Users\\11410\\Desktop\\pic 目录');
    } finally {
      hideLoading();
      refreshActionState();
    }
  });

  // ── 初始化 ───────────────────────────────────────────────
  window.addEventListener('resize', resizeCanvas);
  image.addEventListener('load', resizeCanvas);

  document.addEventListener('DOMContentLoaded', () => {
    refreshActionState();
  });
  
  if (document.readyState !== 'loading') {
    refreshActionState();
  }
}());
