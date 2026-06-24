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

  function setStatus(text) { const n = $('rl-status'); if (n) n.textContent = text; }

  // ── 选中配方的参数（标准坐标 / 允许偏差 / 阈值） ───────────
  function selectedOption() {
    const sel = $('recipe-id');
    return sel && sel.value ? sel.options[sel.selectedIndex] : null;
  }
  function currentRecipeData() {
    const opt = selectedOption();
    const data = { layer_no: Number($('layer-no').value || 1) };
    if (opt) {
      data.standard_x = Number(opt.dataset.sx || 0);
      data.standard_y = Number(opt.dataset.sy || 0);
      data.standard_z = Number(opt.dataset.sz || 0);
      data.max_offset_x = Number(opt.dataset.mox || 20);
      data.max_offset_y = Number(opt.dataset.moy || 20);
      data.max_offset_z = Number(opt.dataset.moz || 20);
      data.confidence_threshold = Number(opt.dataset.conf || 0.7);
    }
    return data;
  }
  function maxOffsets() {
    const opt = selectedOption();
    return {
      x: opt ? Number(opt.dataset.mox || 20) : 20,
      y: opt ? Number(opt.dataset.moy || 20) : 20,
      z: opt ? Number(opt.dataset.moz || 20) : 20,
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
      const data = await postJson(CFG.captureUrl, { recipe_id: $('recipe-id').value || null });
      if (!data.success) { setStatus(data.error || '采集失败'); return; }
      state.token = data.pointcloud_token;
      state.roi = null; state.displayRoi = null;
      image.src = data.preview_image_url + '?t=' + Date.now();
      image.dataset.naturalWidth = data.image_width;
      image.dataset.naturalHeight = data.image_height;
      image.style.display = 'block';
      canvas.style.display = 'block';
      $('rl-placeholder').style.display = 'none';
      $('rl-roi-readout').style.display = 'block';
      $('rl-source').textContent = '数据源 ' + (data.source || '—');
      setReadout();
      setStatus('点云已采集，请在图上拖拽绘制 ROI。');
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
    if (!state.roi) { setStatus('请先在图上绘制 ROI。'); return; }
    showLoading('计算坐标偏差中...');
    try {
      const data = await postJson(CFG.calculateUrl, {
        pointcloud_token: state.token,
        roi_config: { target_roi: state.roi },
        recipe_id: $('recipe-id').value || null,
        recipe_data: currentRecipeData(),
        layer_no: Number($('layer-no').value || 1),
      });
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
      const data = await postJson(CFG.saveUrl, {
        pointcloud_token: state.token,
        roi_config: { target_roi: state.roi },
        recipe_id: $('recipe-id').value || null,
        recipe_data: currentRecipeData(),
        position_no: Number($('position-no').value || 1),
        layer_no: Number($('layer-no').value || 1),
      });
      if (!data.success) { setStatus(data.error || '保存失败'); return; }
      setStatus('结果已保存到数据库。');
      loadHistory();
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); }
  });

  // ── 渲染结果 ─────────────────────────────────────────────
  function renderResult(r) {
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
        layer_no: Number($('layer-no').value || 1),
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

  // ── 配方选择联动 POS/层号 ─────────────────────────────────
  $('recipe-id').addEventListener('change', () => {
    const opt = selectedOption();
    if (opt && opt.dataset.pos) $('position-no').value = opt.dataset.pos;
    if (opt && opt.dataset.layer) $('layer-no').value = opt.dataset.layer;
  });

  $('btn-refresh-history').addEventListener('click', loadHistory);
  window.addEventListener('resize', resizeCanvas);
  image.addEventListener('load', resizeCanvas);

  document.addEventListener('DOMContentLoaded', loadHistory);
  if (document.readyState !== 'loading') loadHistory();
}());
