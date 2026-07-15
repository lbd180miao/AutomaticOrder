(function () {
  'use strict';

  const root = document.getElementById('real-workbench');
  if (!root) return;

  const $ = (sel) => root.querySelector(sel);
  const $$ = (sel) => Array.from(root.querySelectorAll(sel));
  const CAPTURE_URL    = root.dataset.captureUrl;
  const LAST_URL       = root.dataset.lastCaptureUrl;
  const csrf           = () => $('[name=csrfmiddlewaretoken]').value;

  const state = { projection: 'xy', result: null };

  // ── 读取当前屏幕上的参数 ──────────────────────────────
  function readMatrix() {
    const m = Array.from({ length: 4 }, () => Array(4).fill(0));
    $$('[data-matrix-row]').forEach((inp) => {
      m[+inp.dataset.matrixRow][+inp.dataset.matrixCol] = Number(inp.value) || 0;
    });
    return m;
  }

  function readGroup(attr) {
    const obj = {};
    $$(`[${attr}]`).forEach((inp) => { obj[inp.getAttribute(attr)] = Number(inp.value) || 0; });
    return obj;
  }

  function buildPayload() {
    return {
      layer_no:       Number($('#real-layer').value),
      hand_eye_matrix: readMatrix(),
      robot_pose:      readGroup('data-pose'),
      theoretical:     readGroup('data-theoretical'),
      roi:             readGroup('data-roi'),
    };
  }

  // ── 将结果写入界面 ────────────────────────────────────
  function writeMatrix(m) {
    $$('[data-matrix-row]').forEach((inp) => {
      inp.value = m[+inp.dataset.matrixRow][+inp.dataset.matrixCol];
    });
  }

  function writeGroup(attr, obj) {
    $$(`[${attr}]`).forEach((inp) => {
      const v = obj[inp.getAttribute(attr)];
      if (v !== undefined) inp.value = v;
    });
  }

  function writeConfig(cfg) {
    if (!cfg) return;
    writeMatrix(cfg.hand_eye_matrix);
    writeGroup('data-pose', cfg.robot_pose);
    writeGroup('data-theoretical', cfg.theoretical);
    writeGroup('data-roi', cfg.roi);
    $('#real-layer').value = cfg.layer_no || 1;
  }

  // ── 渲染点云 + 结果数值 ───────────────────────────────
  function render(data) {
    state.result = data;

    // 更新点数
    ['camera', 'base', 'roi'].forEach((name) => {
      $(`#real-${name}-count`).textContent = `${data.point_counts[name]} 点`;
      draw($(`#real-${name}-cloud`), data[`${name}_points`],
        name === 'roi'    ? '#34d399' :
        name === 'base'   ? '#38bdf8' : '#818cf8');
      const range = data.coordinate_ranges[name];
      const s2 = state.projection === 'xy' ? 'y' : 'z';
      $(`#real-${name}-range`).textContent =
        `X ${fmt(range.x_min)} ～ ${fmt(range.x_max)} / ${s2.toUpperCase()} ${fmt(range[`${s2}_min`])} ～ ${fmt(range[`${s2}_max`])} mm`;
    });

    // 偏差数值
    ['x', 'y', 'z'].forEach((axis) => {
      $(`#real-result-${axis}-theoretical`).textContent = fmt(data.theoretical[axis]);
      $(`#real-result-${axis}-actual`).textContent      = fmt(data.actual[axis]);
      const offEl = $(`#real-result-${axis}-offset`);
      const offVal = data.offset[axis];
      offEl.textContent = signed(offVal);
      offEl.className = 'real-offset ' + (Math.abs(offVal) < 0.5 ? 'zero' : offVal > 0 ? 'positive' : 'negative');
    });

    // 采集时间
    if (data.captured_at) {
      $(`#real-capture-time`).textContent = `最近采集：${data.captured_at}`;
      $('#real-last-captured strong').textContent = data.captured_at;
    }
  }

  // ── Canvas 绘图 ───────────────────────────────────────
  function draw(canvas, points, color) {
    const ratio  = window.devicePixelRatio || 1;
    const width  = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width  = width  * ratio;
    canvas.height = height * ratio;
    const ctx = canvas.getContext('2d');
    ctx.scale(ratio, ratio);
    ctx.clearRect(0, 0, width, height);

    if (!points || !points.length) {
      ctx.fillStyle = '#334155';
      ctx.font = '13px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('等待采集…', width / 2, height / 2);
      return;
    }

    const si = state.projection === 'xy' ? 1 : 2;
    const xs = points.map((p) => p[0]);
    const ys = points.map((p) => p[si]);
    let minX = Math.min(...xs), maxX = Math.max(...xs);
    let minY = Math.min(...ys), maxY = Math.max(...ys);
    if (maxX === minX) maxX += 1;
    if (maxY === minY) maxY += 1;

    const pad = 18;
    ctx.strokeStyle = '#1e293b';
    ctx.strokeRect(pad, pad, width - pad * 2, height - pad * 2);
    ctx.fillStyle = color;
    points.forEach((p) => {
      const x = pad + (p[0] - minX) / (maxX - minX) * (width  - pad * 2);
      const y = height - pad - (p[si] - minY) / (maxY - minY) * (height - pad * 2);
      ctx.fillRect(x, y, 2, 2);
    });
  }

  // ── 状态栏 ────────────────────────────────────────────
  function setStatus(msg, type) {
    const el = $('#real-status');
    el.textContent = msg;
    el.className = `coordinate-status${type ? ` is-${type}` : ''}`;
  }

  function fmt(v)    { return Number(v).toFixed(3); }
  function signed(v) { const n = Number(v); return `${n >= 0 ? '+' : ''}${n.toFixed(3)}`; }

  // ── 核心：采集真实点云 ─────────────────────────────────
  async function captureReal() {
    const btns = [document.getElementById('btn-capture-real'),
                  document.getElementById('btn-capture-real-2')];

    // 校验必填字段
    const roi = readGroup('data-roi');
    for (const axis of ['x', 'y', 'z']) {
      if (roi[`${axis}_min`] >= roi[`${axis}_max`]) {
        alert(`ROI 设置错误：${axis.toUpperCase()} Min 必须小于 Max`);
        return;
      }
    }

    // 加载状态
    btns.forEach((b) => { if (b) { b.disabled = true; b.classList.add('is-loading'); b.textContent = '采集中…'; } });
    setStatus('正在连接相机并采集点云，请稍候…');

    try {
      const resp = await fetch(CAPTURE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
        body: JSON.stringify(buildPayload()),
      });
      const payload = await resp.json();

      if (!resp.ok || !payload.success) {
        const msg = payload.error && payload.error.message || '采集失败';
        alert(`⚠️ 相机采集失败\n\n${msg}\n\n请检查：\n1. 相机是否已连接并开启数据流\n2. dm_camera 模块是否正常运行`);
        setStatus(`采集失败：${msg}`, 'error');
        return;
      }

      const data = payload.data;
      if (data.config) writeConfig(data.config);
      render(data);
      setStatus(`✅ 采集完成 · ${data.captured_at} · 相机 ${data.point_counts.camera} 点 → ROI ${data.point_counts.roi} 点`, 'success');

    } catch (err) {
      alert(`⚠️ 网络请求失败\n\n${err.message}`);
      setStatus(`请求失败：${err.message}`, 'error');
    } finally {
      btns.forEach((b) => {
        if (b) {
          b.disabled = false;
          b.classList.remove('is-loading');
          b.textContent = b.id === 'btn-capture-real-2' ? '📡 采集真实点云' : '📡 采集真实点云';
        }
      });
    }
  }

  // ── 加载上次结果 ──────────────────────────────────────
  async function loadLastCapture() {
    try {
      const resp = await fetch(LAST_URL);
      const payload = await resp.json();
      if (payload.success && payload.data) {
        const data = payload.data;
        if (data.config) writeConfig(data.config);
        render(data);
        setStatus(`已加载上次采集结果（${data.captured_at || '时间未知'}）`, 'success');
      } else {
        setStatus('尚无历史采集数据，请填写参数后点击「采集真实点云」', '');
      }
    } catch (_) {
      setStatus('请填写手眼矩阵和机器人位姿后，点击「📡 采集真实点云」开始测试', '');
    }
  }

  // ── 初始化默认矩阵（单位矩阵）────────────────────────
  function initIdentity() {
    $$('[data-matrix-row]').forEach((inp) => {
      const r = +inp.dataset.matrixRow;
      const c = +inp.dataset.matrixCol;
      inp.value = (r === c) ? 1 : 0;
    });
  }

  // ── 事件绑定 ──────────────────────────────────────────
  document.getElementById('btn-capture-real')?.addEventListener('click', captureReal);
  document.getElementById('btn-capture-real-2')?.addEventListener('click', captureReal);
  document.getElementById('btn-load-last')?.addEventListener('click', loadLastCapture);

  $$('[data-projection]').forEach((btn) =>
    btn.addEventListener('click', () => {
      state.projection = btn.dataset.projection;
      $$('[data-projection]').forEach((b) => b.classList.toggle('is-active', b === btn));
      if (state.result) render(state.result);
    })
  );

  window.addEventListener('resize', () => { if (state.result) render(state.result); });

  // ── 启动：先加载上次结果，再初始化空矩阵（如果没有历史数据）
  initIdentity();
  loadLastCapture();

}());
