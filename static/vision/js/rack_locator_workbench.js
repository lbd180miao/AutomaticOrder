/* ============================================================
 *  3D 料架定位工作台 · 交互逻辑
 *  采集点云 → 画 ROI → 计算偏差 → 保存到数据库
 *  次级：按 POS/层号自动拍照计算 + 历史记录
 * ============================================================ */
(function () {
  const CFG = window.rackLocatorConfig || {};
  const $ = (id) => document.getElementById(id);
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

  // 工作台状态
  const state = {
    token: null,         // 持久化点云 token
    roi: null,           // 真实图像像素 ROI {x,y,w,h}
    drawing: false,
    start: null,
    displayRoi: null,
    lastResultId: null,
    sdkConfigId: null,
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
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify(body || {}),
    });
    return res.json();
  }

  async function sendJson(url, method, body) {
    const options = {
      method,
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
    };
    if (body !== undefined) options.body = JSON.stringify(body || {});
    const res = await fetch(url, options);
    return res.json();
  }

  function setStatus(text) { const n = $('rl-status'); if (n) n.textContent = text; }
  function setSdkStatus(text) { const n = $('sdk-status'); if (n) n.textContent = text; }

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

  function boolSelect(id, fallback) {
    const node = $(id);
    if (!node) return fallback;
    return node.value === 'true';
  }

  function sdkConfigPayload() {
    return {
      name: $('sdk-config-name')?.value || '3D料架定位SDK',
      device_sn: $('sdk-device-sn')?.value || '',
      frame_rate: numberInput('sdk-frame-rate', 10),
      exposure_time: numberInput('sdk-exposure-time', 1000),
      trigger_mode: $('sdk-trigger-mode')?.value || 'ACTIVE',
      confidence_filter_enable: true,
      confidence_threshold: numberInput('sdk-confidence-threshold', 15),
      flying_pixels_filter_enable: true,
      flying_pixels_threshold: numberInput('sdk-flying-pixels-threshold', 5),
      spatial_filter_enable: true,
      spatial_threshold: numberInput('sdk-spatial-threshold', 5),
      is_active: true,
    };
  }

  function fillSdkConfig(config) {
    state.sdkConfigId = config?.id || null;
    if (!config) return;
    if ($('sdk-config-name')) $('sdk-config-name').value = config.name || '3D料架定位SDK';
    if ($('sdk-device-sn')) $('sdk-device-sn').value = config.device_sn || '';
    if ($('sdk-frame-rate')) $('sdk-frame-rate').value = config.frame_rate ?? 10;
    if ($('sdk-exposure-time')) $('sdk-exposure-time').value = config.exposure_time ?? 1000;
    if ($('sdk-trigger-mode')) $('sdk-trigger-mode').value = config.trigger_mode || 'ACTIVE';
    if ($('sdk-confidence-threshold')) $('sdk-confidence-threshold').value = config.confidence_threshold ?? 15;
    if ($('sdk-flying-pixels-threshold')) $('sdk-flying-pixels-threshold').value = config.flying_pixels_threshold ?? 5;
    if ($('sdk-spatial-threshold')) $('sdk-spatial-threshold').value = config.spatial_threshold ?? 5;
  }

  async function loadSdkConfig() {
    try {
      const data = await sendJson(CFG.apiSdkConfigsUrl, 'GET');
      if (!data.success) { setSdkStatus(data.error || '读取配置失败'); return; }
      const configs = data.data?.configs || [];
      const active = configs.find((cfg) => cfg.is_active) || configs[0];
      if (active) {
        fillSdkConfig(active);
        setSdkStatus(`已读取当前配置：${active.name}`);
      } else {
        setSdkStatus('暂无 SDK 配置，可填写参数后保存为当前配置。');
      }
    } catch (e) {
      setSdkStatus('读取配置失败：' + e.message);
    }
  }

  // ── 选中配方的参数（标准坐标 / 允许偏差 / 阈值） ───────────
  // 新方案：配方选择改为卡片点击，数据存放在 .rl-recipe-card.selected 的 dataset 上
  function selectedCardData() {
    const card = document.querySelector('.rl-recipe-card.selected');
    return card ? card.dataset : null;
  }
  function currentRecipeData() {
    const d = selectedCardData();
    const data = { layer_no: currentLayerNo() };
    if (d) {
      data.standard_x = Number(d.sx || 0);
      data.standard_y = Number(d.sy || 0);
      data.standard_z = Number(d.sz || 0);
      data.max_offset_x = Number(d.mox || 20);
      data.max_offset_y = Number(d.moy || 20);
      data.max_offset_z = Number(d.moz || 20);
      data.confidence_threshold = Number(d.conf || 0.7);
    }
    return data;
  }
  function maxOffsets() {
    const d = selectedCardData();
    return {
      x: d ? Number(d.mox || 20) : 20,
      y: d ? Number(d.moy || 20) : 20,
      z: d ? Number(d.moz || 20) : 20,
    };
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
  });

  // ── 采集点云 ─────────────────────────────────────────────
  $('btn-capture').addEventListener('click', async () => {
    showLoading('3D 相机采集中...');
    try {
      const raw = await postJson(CFG.captureUrl || CFG.legacyCaptureUrl, {
        recipe_id: $('recipe-id').value || null,
        rack_side: currentRackSide(),
        layer_no: currentLayerNo(),
      });
      const data = apiPayload(raw);
      if (!data.success) { setStatus(data.error || '采集失败'); return; }
      state.token = data.pointcloud_token;
      state.roi = null; state.displayRoi = null;
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
      if (data.source && data.source.indexOf('sample') === 0) {
        setStatus('⚠ 未取到真实相机数据，已回退模拟点云'
          + (data.fallback_reason ? '：' + data.fallback_reason : '（相机未连接）')
          + '。请检查相机连接后重试。');
      } else {
        setStatus('点云已采集（真实相机），请在图上拖拽绘制 ROI。');
      }
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); }
  });

  $('btn-redraw').addEventListener('click', () => {
    state.roi = null; state.displayRoi = null;
    draw(); setReadout();
    setStatus('请重新拖拽绘制 ROI。');
  });

  // ── 计算偏差 ─────────────────────────────────────────────
  $('btn-calculate').addEventListener('click', async () => {
    if (!state.token) { setStatus('请先采集点云。'); return; }
    showLoading('计算坐标偏差中...');
    try {
      const raw = await postJson(CFG.testLocateUrl || CFG.legacyCalculateUrl, {
        pointcloud_token: state.token,
        roi: currentRoi3D(),
        roi_config: { target_roi: state.roi },
        rack_side: currentRackSide(),
        recipe_id: $('recipe-id').value || null,
        recipe_data: currentRecipeData(),
        layer_no: currentLayerNo(),
      });
      const data = apiPayload(raw);
      if (!data.success) { setStatus(data.error || '计算失败'); return; }
      renderResult(data.result);
      $('btn-save').disabled = false;
      $('last-time').textContent = '上次计算：' + new Date().toLocaleString('zh-CN', { hour12: false });
      setStatus(data.result.locate_ok ? '计算完成：定位 OK。' : ('计算完成：定位 NG · ' + (data.result.error_message || data.result.error_code || '')));
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); }
  });

  // ── 保存结果到数据库 ─────────────────────────────────────
  $('btn-save').addEventListener('click', async () => {
    if (!state.token || !state.roi) return;
    showLoading('保存结果中...');
    try {
      const data = await postJson(CFG.legacySaveUrl || CFG.saveUrl, {
        pointcloud_token: state.token,
        roi_config: { target_roi: state.roi },
        recipe_id: $('recipe-id').value || null,
        recipe_data: currentRecipeData(),
        position_no: Number($('position-no').value || 1),
        layer_no: currentLayerNo(),
      });
      if (!data.success) { setStatus(data.error || '保存失败'); return; }
      setStatus('结果已保存到数据库。');
      loadHistory();
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); }
  });

  $('btn-auto-align')?.addEventListener('click', async () => {
    if (!state.token) { setStatus('请先采集点云。'); return; }
    showLoading('自动对齐 ROI 中...');
    try {
      const raw = await postJson(CFG.autoAlignUrl, {
        pointcloud_token: state.token,
        rack_side: currentRackSide(),
        layer_no: currentLayerNo(),
        roi: currentRoi3D(),
      });
      const data = apiPayload(raw);
      if (!data.success) { setStatus(data.error || '自动对齐失败'); return; }
      const roi = data.roi || data.roi_3d || {};
      Object.entries({
        'roi-x-min': roi.x_min,
        'roi-x-max': roi.x_max,
        'roi-y-min': roi.y_min,
        'roi-y-max': roi.y_max,
        'roi-z-min': roi.z_min,
        'roi-z-max': roi.z_max,
      }).forEach(([id, value]) => {
        if ($(id) && value != null) $(id).value = Number(value).toFixed(3);
      });
      setStatus('自动对齐完成，可执行试定位。');
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); }
  });

  $('btn-save-roi')?.addEventListener('click', async () => {
    showLoading('保存 3D ROI 中...');
    try {
      const raw = await postJson(CFG.saveRoiUrl, {
        recipe_id: $('recipe-id').value || null,
        rack_side: currentRackSide(),
        layer_no: currentLayerNo(),
        mode: currentMode(),
        name: `${currentRackSide()}-L${currentLayerNo()}-${currentMode()}`,
        ...currentRoi3D(),
      });
      const data = apiPayload(raw);
      if (!data.success) { setStatus(data.error || '保存 ROI 失败'); return; }
      setStatus('3D ROI 已保存。');
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); }
  });

  $('btn-write-plc')?.addEventListener('click', async () => {
    if (!state.lastResultId) { setStatus('请先完成一次定位计算。'); return; }
    showLoading('写入 PLC 中...');
    try {
      const raw = await postJson(CFG.writePlcUrl, { result_id: state.lastResultId });
      const data = apiPayload(raw);
      if (!data.success) { setStatus(data.error || 'PLC 写入失败'); return; }
      setStatus('定位结果已写入 PLC。');
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); }
  });

  $('btn-sdk-debug')?.addEventListener('click', () => {
    $('sdk-debug-drawer')?.classList.add('open');
    $('sdk-drawer-backdrop')?.classList.add('open');
    loadSdkConfig();
  });
  function closeSdkDrawer() {
    $('sdk-debug-drawer')?.classList.remove('open');
    $('sdk-drawer-backdrop')?.classList.remove('open');
  }
  $('btn-sdk-close')?.addEventListener('click', closeSdkDrawer);
  $('sdk-drawer-backdrop')?.addEventListener('click', closeSdkDrawer);

  $('btn-sdk-load-config')?.addEventListener('click', loadSdkConfig);

  $('btn-sdk-save-config')?.addEventListener('click', async () => {
    setSdkStatus('保存 SDK 配置中...');
    try {
      const payload = sdkConfigPayload();
      const url = state.sdkConfigId
        ? `/dm-camera/api/configs/${state.sdkConfigId}/update/`
        : CFG.apiSdkCreateConfigUrl;
      const data = await sendJson(url, state.sdkConfigId ? 'PUT' : 'POST', payload);
      if (!data.success) { setSdkStatus(data.error || '保存配置失败'); return; }
      if (!state.sdkConfigId && data.data?.id) state.sdkConfigId = data.data.id;
      setSdkStatus('已保存为当前全局 SDK 配置，正式采集将复用该配置。');
      await loadSdkConfig();
    } catch (e) {
      setSdkStatus('保存配置失败：' + e.message);
    }
  });

  $('btn-sdk-find-devices')?.addEventListener('click', async () => {
    setSdkStatus('查找设备中...');
    try {
      const data = await sendJson(CFG.apiSdkFindDevicesUrl, 'GET');
      const list = $('sdk-device-list');
      if (!data.success) { setSdkStatus(data.error || '查找设备失败'); return; }
      const devices = data.data?.devices || [];
      if (list) {
        list.innerHTML = devices.length
          ? devices.map((d) => `<button type="button" class="btn btn-secondary btn-sm sdk-device-pick" data-sn="${d.sn || ''}">${d.sn || '未知SN'} ${d.ip || ''}</button>`).join('')
          : '未找到设备';
        list.querySelectorAll('.sdk-device-pick').forEach((btn) => {
          btn.addEventListener('click', () => {
            if ($('sdk-device-sn')) $('sdk-device-sn').value = btn.dataset.sn || '';
            setSdkStatus('已选择设备：' + (btn.dataset.sn || '默认设备'));
          });
        });
      }
      setSdkStatus(devices.length ? `找到 ${devices.length} 台设备` : '未找到设备');
    } catch (e) {
      setSdkStatus('查找设备失败：' + e.message);
    }
  });

  $('btn-sdk-connect')?.addEventListener('click', async () => {
    setSdkStatus('连接设备中...');
    try {
      const data = await sendJson(CFG.apiSdkConnectUrl, 'POST', {
        device_sn: $('sdk-device-sn')?.value || null,
        config_id: state.sdkConfigId,
      });
      setSdkStatus(data.success ? '设备已连接。' : (data.error || '连接失败'));
    } catch (e) {
      setSdkStatus('连接失败：' + e.message);
    }
  });

  $('btn-sdk-disconnect')?.addEventListener('click', async () => {
    try {
      const data = await sendJson(CFG.apiSdkDisconnectUrl, 'POST', {});
      setSdkStatus(data.success ? '设备已断开。' : (data.error || '断开失败'));
    } catch (e) {
      setSdkStatus('断开失败：' + e.message);
    }
  });

  $('btn-sdk-start-stream')?.addEventListener('click', async () => {
    try {
      const data = await sendJson(CFG.apiSdkStartStreamUrl, 'POST', {});
      setSdkStatus(data.success ? '数据流已开启。' : (data.error || '开启数据流失败'));
    } catch (e) {
      setSdkStatus('开启数据流失败：' + e.message);
    }
  });

  $('btn-sdk-stop-stream')?.addEventListener('click', async () => {
    try {
      const data = await sendJson(CFG.apiSdkStopStreamUrl, 'POST', {});
      setSdkStatus(data.success ? '数据流已停止。' : (data.error || '停止数据流失败'));
    } catch (e) {
      setSdkStatus('停止数据流失败：' + e.message);
    }
  });

  $('btn-sdk-capture')?.addEventListener('click', async () => {
    setSdkStatus('测试采集中...');
    try {
      const data = await sendJson(CFG.apiSdkCaptureUrl, 'POST', {
        frame_type: $('sdk-frame-type')?.value || 'POINTCLOUD',
        save_record: boolSelect('sdk-save-record', true),
      });
      if (!data.success) { setSdkStatus(data.error || '测试采集失败'); return; }
      const payload = data.data || {};
      const preview = $('sdk-preview');
      if (preview) {
        preview.innerHTML = payload.preview_url
          ? `<img src="${payload.preview_url}?t=${Date.now()}" alt="SDK 采集预览">`
          : `采集成功：${payload.frame_type || ''} ${payload.width || '-'} x ${payload.height || '-'}`;
      }
      setSdkStatus('测试采集完成。');
    } catch (e) {
      setSdkStatus('测试采集失败：' + e.message);
    }
  });

  // ── 渲染结果 ─────────────────────────────────────────────
  function renderResult(r) {
    state.lastResultId = r.id || r.result_id || state.lastResultId || null;
    const ok = r.locate_ok ?? r.is_success;
    const v = $('rl-verdict');
    v.className = 'rl-verdict ' + (ok ? 'ok' : 'fail');
    $('rl-verdict-icon').textContent = ok ? '✅' : '❌';
    $('rl-verdict-text').textContent = ok ? '定位 OK · 坐标偏差在允许范围' : '定位 NG · 请核查';
    $('rl-verdict-sub').textContent = ok ? '可保存结果到数据库' : (r.error_message || r.error_code || '置信度或偏差超限');

    const mo = maxOffsets();
    setOffset('x', r.offset_x, mo.x);
    setOffset('y', r.offset_y, mo.y);
    setOffset('z', r.offset_z, mo.z);
    setOffset('rz', r.offset_rz, null);

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
    $('d-ax').textContent = Number(r.actual_x || 0).toFixed(2);
    $('d-ay').textContent = Number(r.actual_y || 0).toFixed(2);
    $('d-az').textContent = Number(r.actual_z || 0).toFixed(2);
    $('d-points').textContent = meta.valid_point_count ?? '—';
    $('rl-detail').style.display = 'flex';
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

  // ── 自动按 POS/层号触发（沿用既有 trigger） ───────────────
  $('btn-auto-trigger').addEventListener('click', async () => {
    showLoading('自动拍照计算中...');
    try {
      const data = await postJson(CFG.triggerUrl, {
        position_no: Number($('position-no').value || 1),
        layer_no: currentLayerNo(),
        rack_side: currentRackSide(),
        recipe_id: $('recipe-id').value || null,
        write_plc: false,
      });
      const status = $('rl-auto-status');
      if (!data.success) { status.textContent = '失败：' + (data.error || '未知错误'); return; }
      renderResult(data.result);
      status.textContent = data.result.locate_ok ? '自动定位 OK，已入库。' : '自动定位 NG，已入库。';
      loadHistory();
    } catch (e) {
      $('rl-auto-status').textContent = '网络请求失败：' + e.message;
    } finally { hideLoading(); }
  });

  // ── 历史记录 ─────────────────────────────────────────────
  async function loadHistory() {
    try {
      const pos = encodeURIComponent($('position-no').value || '');
      const layer = encodeURIComponent($('layer-no').value || '');
      const res = await fetch(`${CFG.resultsUrl}?position_no=${pos}&layer_no=${layer}`);
      const data = await res.json();
      const tbody = $('history-tbody');
      if (!data.results || !data.results.length) {
        tbody.innerHTML = '<tr><td colspan="9" class="empty">暂无定位记录</td></tr>';
        return;
      }
      tbody.innerHTML = data.results.map((r) => `
        <tr>
          <td>${(r.created_at || '').replace('T', ' ').slice(0, 19) || '—'}</td>
          <td>${r.position_no ?? '—'}</td>
          <td>${r.layer_no ?? '—'}</td>
          <td>${fmt(r.offset_x)}</td>
          <td>${fmt(r.offset_y)}</td>
          <td>${fmt(r.offset_z)}</td>
          <td>${fmt(r.offset_rz, '°')}</td>
          <td>${r.confidence != null ? (r.confidence * 100).toFixed(1) + '%' : '—'}</td>
          <td>${(r.locate_ok ?? r.is_success) ? '<span class="badge badge-ok">OK</span>' : '<span class="badge badge-fail">NG</span>'}</td>
        </tr>`).join('');
    } catch (e) {
      $('history-tbody').innerHTML = `<tr><td colspan="9" class="empty">加载失败：${e.message}</td></tr>`;
    }
  }
  function fmt(v, unit = 'mm') {
    const n = parseFloat(v);
    return isNaN(n) ? '—' : (n > 0 ? '+' : '') + n.toFixed(3) + ' ' + unit;
  }

  // ── 配方卡片选择联动 POS/层号（已由 HTML 层 selectRecipeCard() 处理，此处仅保留历史兼容） ──
  // $('recipe-id').addEventListener('change', ...) 已迁移到 HTML 内联 onclick

  $('btn-refresh-history').addEventListener('click', loadHistory);
  window.addEventListener('resize', resizeCanvas);
  image.addEventListener('load', resizeCanvas);

  document.addEventListener('DOMContentLoaded', loadHistory);
  if (document.readyState !== 'loading') loadHistory();
}());
