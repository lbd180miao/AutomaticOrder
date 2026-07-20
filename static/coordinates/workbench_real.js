/**
 * workbench_real.js  v20260716-4
 * REAL 实机模式工作台前端逻辑
 *
 * 新增功能：
 *  - 手眼矩阵「保存」→ 写入 localStorage，下次打开自动恢复
 *  - 手眼矩阵「重置」→ 恢复为系统默认值（api_workbench）
 *  - 机器人拍照位「保存」→ 同上
 *  - 机器人拍照位「重置」→ 同上
 *  - 优先级：localStorage 手动保存 > 历史采集 > 系统默认
 */
(function () {
  'use strict';

  const root = document.getElementById('real-workbench');
  if (!root) return;

  const $  = (sel) => root.querySelector(sel);
  const $$ = (sel) => Array.from(root.querySelectorAll(sel));

  const CAPTURE_URL   = root.dataset.captureUrl;
  const LAST_URL      = root.dataset.lastCaptureUrl;
  const WORKBENCH_URL = root.dataset.workbenchUrl;
  const csrf          = () => ($('[name=csrfmiddlewaretoken]') || {}).value || '';

  // localStorage 键名
  const LS_MATRIX = 'real_wb_hand_eye_matrix';
  const LS_POSE   = 'real_wb_robot_pose';

  const state = { projection: 'xy', result: null, defaults: null };

  // ── localStorage 工具 ────────────────────────────────
  function lsSave(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) {}
  }
  function lsLoad(key) {
    try { return JSON.parse(localStorage.getItem(key)); } catch (_) { return null; }
  }
  function lsRemove(key) {
    try { localStorage.removeItem(key); } catch (_) {}
  }

  // ── 读取表单参数 ──────────────────────────────────────
  function readMatrix() {
    const m = Array.from({ length: 4 }, () => Array(4).fill(0));
    $$('[data-matrix-row]').forEach(inp => {
      m[+inp.dataset.matrixRow][+inp.dataset.matrixCol] = Number(inp.value) || 0;
    });
    return m;
  }

  function readGroup(attr) {
    const obj = {};
    $$(`[${attr}]`).forEach(inp => {
      obj[inp.getAttribute(attr)] = Number(inp.value) || 0;
    });
    return obj;
  }

  function isRoiBlank() {
    const r = readGroup('data-roi');
    return ['x_min','x_max','y_min','y_max','z_min','z_max'].every(k => r[k] === 0);
  }

  function hasInvalidRoi() {
    const r = readGroup('data-roi');
    return ['x','y','z'].some(a => r[`${a}_min`] >= r[`${a}_max`]);
  }

  function buildPayload() {
    return {
      layer_no:        Number($('#real-layer').value),
      hand_eye_matrix: readMatrix(),
      robot_pose:      readGroup('data-pose'),
      theoretical:     readGroup('data-theoretical'),
      roi:             readGroup('data-roi'),
    };
  }

  // ── 写入表单 ──────────────────────────────────────────
  function writeMatrix(m) {
    if (!m) return;
    $$('[data-matrix-row]').forEach(inp => {
      const v = (m[+inp.dataset.matrixRow] || [])[+inp.dataset.matrixCol];
      if (v !== undefined) inp.value = v;
    });
  }

  function writeGroup(attr, obj) {
    if (!obj) return;
    $$(`[${attr}]`).forEach(inp => {
      const v = obj[inp.getAttribute(attr)];
      if (v !== undefined && v !== null)
        inp.value = typeof v === 'number' ? +v.toFixed(4) : v;
    });
  }

  function writeConfig(cfg) {
    if (!cfg) return;
    writeMatrix(cfg.hand_eye_matrix);
    writeGroup('data-pose',        cfg.robot_pose);
    writeGroup('data-theoretical', cfg.theoretical);
    writeGroup('data-roi',         cfg.roi);
    if (cfg.layer_no != null) $('#real-layer').value = cfg.layer_no;
  }

  // ── 提示条动画 ────────────────────────────────────────
  function showTip(tipId, msg, type /* 'saved' | 'reset' */) {
    const el = $(`#${tipId}`);
    if (!el) return;
    el.textContent = msg;
    el.className = `card-save-tip tip-${type} show`;
    clearTimeout(el._timer);
    el._timer = setTimeout(() => { el.className = 'card-save-tip'; }, 2800);
  }

  // ── 从 api_workbench 拉取系统默认参数 ───────────────
  async function fetchDefaults(layerNo) {
    if (!WORKBENCH_URL) return null;
    try {
      const layer = layerNo != null ? layerNo : (Number($('#real-layer').value) || 1);
      const resp  = await fetch(`${WORKBENCH_URL}?layer_no=${layer}`);
      if (!resp.ok) return null;
      const payload = await resp.json();
      if (payload.success && payload.data && payload.data.config) {
        state.defaults = payload.data.config;   // 缓存默认值
        return payload.data.config;
      }
    } catch (_) {}
    return null;
  }

  async function loadDefaults(layerNo) {
    const cfg = state.defaults || await fetchDefaults(layerNo);
    if (!cfg) return false;
    writeConfig(cfg);
    return true;
  }

  // ── 保存 / 重置：手眼矩阵 ────────────────────────────
  function saveMatrix() {
    const m = readMatrix();
    lsSave(LS_MATRIX, m);
    const btn = $('#btn-matrix-save');
    if (btn) { btn.classList.add('is-saved'); setTimeout(() => btn.classList.remove('is-saved'), 2500); }
    showTip('matrix-save-tip', '✅ 手眼矩阵已保存到本地，下次打开自动填入', 'saved');
  }

  async function resetMatrix() {
    // 清除本地存储
    lsRemove(LS_MATRIX);
    // 恢复系统默认
    const cfg = state.defaults || await fetchDefaults();
    if (cfg && cfg.hand_eye_matrix) {
      writeMatrix(cfg.hand_eye_matrix);
      showTip('matrix-save-tip', '↺ 已重置为系统默认矩阵（本地保存已清除）', 'reset');
    } else {
      // 无法获取默认值时，恢复单位矩阵
      initIdentity();
      showTip('matrix-save-tip', '↺ 已重置为单位矩阵', 'reset');
    }
  }

  // ── 保存 / 重置：机器人位姿 ──────────────────────────
  function savePose() {
    const pose = readGroup('data-pose');
    lsSave(LS_POSE, pose);
    const btn = $('#btn-pose-save');
    if (btn) { btn.classList.add('is-saved'); setTimeout(() => btn.classList.remove('is-saved'), 2500); }
    showTip('pose-save-tip', '✅ 机器人拍照位已保存到本地，下次打开自动填入', 'saved');
  }

  async function resetPose() {
    lsRemove(LS_POSE);
    const cfg = state.defaults || await fetchDefaults();
    if (cfg && cfg.robot_pose) {
      writeGroup('data-pose', cfg.robot_pose);
      showTip('pose-save-tip', '↺ 已重置为系统默认位姿（本地保存已清除）', 'reset');
    } else {
      $$('[data-pose]').forEach(inp => { inp.value = ''; });
      showTip('pose-save-tip', '↺ 已清空机器人位姿', 'reset');
    }
  }

  // ── 渲染点云 + 结果 ───────────────────────────────────
  function render(data) {
    state.result = data;

    ['camera', 'base', 'roi'].forEach(name => {
      const cnt   = (data.point_counts || {})[name] || 0;
      const pts   = data[`${name}_points`] || [];
      const range = (data.coordinate_ranges || {})[name] || {};
      const color = name === 'roi' ? '#34d399' : name === 'base' ? '#38bdf8' : '#818cf8';

      $(`#real-${name}-count`).textContent = `${cnt} 点`;
      draw($(`#real-${name}-cloud`), pts, color);

      const s2 = state.projection === 'xy' ? 'y' : 'z';
      $(`#real-${name}-range`).textContent = range.x_min !== undefined
        ? `X ${fmt(range.x_min)} ～ ${fmt(range.x_max)} / ${s2.toUpperCase()} ${fmt(range[`${s2}_min`])} ～ ${fmt(range[`${s2}_max`])} mm`
        : '–';
    });

    ['x', 'y', 'z'].forEach(axis => {
      $(`#real-result-${axis}-theoretical`).textContent = fmt((data.theoretical || {})[axis]);
      $(`#real-result-${axis}-actual`).textContent      = fmt((data.actual || {})[axis]);
      const offEl  = $(`#real-result-${axis}-offset`);
      const offVal = ((data.offset || {})[axis]) || 0;
      offEl.textContent = signed(offVal);
      offEl.className   = 'real-offset ' + (
        Math.abs(offVal) < 0.5 ? 'zero' : offVal > 0 ? 'positive' : 'negative'
      );
    });

    if (data.captured_at) {
      $(`#real-capture-time`).textContent        = `最近采集：${data.captured_at}`;
      $('#real-last-captured strong').textContent = data.captured_at;
    }
  }

  // ── Canvas 绘图 ───────────────────────────────────────
  function draw(canvas, points, color) {
    if (!canvas) return;
    const ratio  = window.devicePixelRatio || 1;
    const width  = canvas.clientWidth  || 300;
    const height = canvas.clientHeight || 200;
    canvas.width  = width  * ratio;
    canvas.height = height * ratio;
    const ctx = canvas.getContext('2d');
    ctx.scale(ratio, ratio);
    ctx.clearRect(0, 0, width, height);

    if (!points || !points.length) {
      ctx.fillStyle = '#334155';
      ctx.font      = '13px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('等待采集…', width / 2, height / 2);
      return;
    }

    const si = state.projection === 'xy' ? 1 : 2;
    const xs = points.map(p => p[0]);
    const ys = points.map(p => p[si]);
    let minX = Math.min(...xs), maxX = Math.max(...xs);
    let minY = Math.min(...ys), maxY = Math.max(...ys);
    if (maxX === minX) maxX += 1;
    if (maxY === minY) maxY += 1;

    const pad = 18;
    ctx.strokeStyle = '#1e293b';
    ctx.strokeRect(pad, pad, width - pad * 2, height - pad * 2);
    ctx.fillStyle = color;
    points.forEach(p => {
      const x = pad + (p[0] - minX) / (maxX - minX) * (width  - pad * 2);
      const y = height - pad - (p[si] - minY) / (maxY - minY) * (height - pad * 2);
      ctx.fillRect(x, y, 2, 2);
    });
  }

  // ── 状态栏 ────────────────────────────────────────────
  function setStatus(msg, type) {
    const el = $('#real-status');
    if (!el) return;
    el.textContent = msg;
    el.className   = `coordinate-status${type ? ` is-${type}` : ''}`;
  }

  function fmt(v)    { return v == null ? '–' : Number(v).toFixed(3); }
  function signed(v) { const n = Number(v || 0); return `${n >= 0 ? '+' : ''}${n.toFixed(3)}`; }

  // ── 核心：采集真实点云 ─────────────────────────────────
  async function captureReal() {
    const btns = [
      document.getElementById('btn-capture-real'),
      document.getElementById('btn-capture-real-2'),
    ];
    const setBusy = busy => btns.forEach(b => {
      if (!b) return;
      b.disabled = busy;
      b.classList.toggle('is-loading', busy);
      b.textContent = busy ? '采集中…' : '📡 采集真实点云';
    });

    // ROI 为空/无效时先自动填充默认参数
    if (isRoiBlank() || hasInvalidRoi()) {
      setStatus('ROI 未设置，正在自动加载默认参数…');
      const ok = await loadDefaults();
      setStatus(ok ? '✅ 默认参数已填入，开始采集…' : '无法加载默认参数，将由后端自动计算 ROI…');
    }

    setBusy(true);
    setStatus('正在连接相机并采集点云，请稍候…');

    try {
      const resp    = await fetch(CAPTURE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
        body: JSON.stringify(buildPayload()),
      });
      const payload = await resp.json();

      if (!resp.ok || !payload.success) {
        const msg = (payload.error && payload.error.message) || '采集失败，请重试';
        setStatus(`❌ ${msg}`, 'error');
        return;
      }

      const data = payload.data;
      // 只把后端自动计算的 ROI 写回；手眼矩阵和位姿不覆盖用户调试值
      if (data.config && data.config.roi) writeGroup('data-roi', data.config.roi);
      if (data.config && data.config.theoretical) writeGroup('data-theoretical', data.config.theoretical);
      render(data);

      const src  = data.source || '';
      const hint = src === 'dm_camera'
        ? '📡 真实相机'
        : src === 'sample_fallback'
          ? '⚠️ 相机不可用，已使用模拟点云（仅供测试）'
          : '';
      setStatus(
        `✅ 采集完成 · ${data.captured_at} · 相机 ${data.point_counts.camera} 点 → ROI ${data.point_counts.roi} 点${hint ? '  |  ' + hint : ''}`,
        src === 'sample_fallback' ? 'warning' : 'success',
      );
    } catch (err) {
      setStatus(`❌ 网络请求失败：${err.message}`, 'error');
    } finally {
      setBusy(false);
    }
  }

  // ── 加载上次结果 ──────────────────────────────────────
  async function loadLastCapture() {
    try {
      const resp    = await fetch(LAST_URL);
      const payload = await resp.json();
      if (payload.success && payload.data) {
        const data = payload.data;
        if (data.config) writeConfig(data.config);
        render(data);
        setStatus(`已加载上次采集结果（${data.captured_at || '时间未知'}）`, 'success');
        return true;
      }
    } catch (_) {}
    return false;
  }

  // ── 初始化矩阵为单位矩阵 ──────────────────────────────
  function initIdentity() {
    $$('[data-matrix-row]').forEach(inp => {
      inp.value = (+inp.dataset.matrixRow === +inp.dataset.matrixCol) ? 1 : 0;
    });
  }

  // ── 事件绑定 ──────────────────────────────────────────
  document.getElementById('btn-capture-real')?.addEventListener('click',  captureReal);
  document.getElementById('btn-capture-real-2')?.addEventListener('click', captureReal);

  document.getElementById('btn-load-last')?.addEventListener('click', async () => {
    const ok = await loadLastCapture();
    if (!ok) setStatus('尚无历史采集数据，请填写参数后点击「采集真实点云」', '');
  });

  document.getElementById('btn-load-defaults')?.addEventListener('click', async () => {
    setStatus('正在加载默认参数…');
    const cfg = await fetchDefaults();
    if (cfg) {
      writeConfig(cfg);
      // 若 localStorage 有保存值则覆盖回来（保留用户调试数据）
      const savedMatrix = lsLoad(LS_MATRIX);
      if (savedMatrix) writeMatrix(savedMatrix);
      const savedPose = lsLoad(LS_POSE);
      if (savedPose) writeGroup('data-pose', savedPose);
      setStatus('✅ 默认参数已填入（已保存的手眼矩阵/位姿已自动还原）', 'success');
    } else {
      setStatus('❌ 获取默认参数失败，请手动填写', 'error');
    }
  });

  // 手眼矩阵按钮
  document.getElementById('btn-matrix-save')?.addEventListener('click',  saveMatrix);
  document.getElementById('btn-matrix-reset')?.addEventListener('click', resetMatrix);

  // 机器人位姿按钮
  document.getElementById('btn-pose-save')?.addEventListener('click',  savePose);
  document.getElementById('btn-pose-reset')?.addEventListener('click', resetPose);

  // 切换层号时自动刷新 ROI（矩阵和位姿不自动覆盖）
  $('#real-layer')?.addEventListener('change', async () => {
    if (isRoiBlank()) {
      const cfg = await fetchDefaults(Number($('#real-layer').value));
      if (cfg) {
        writeGroup('data-roi',         cfg.roi);
        writeGroup('data-theoretical', cfg.theoretical);
      }
    }
  });

  $$('[data-projection]').forEach(btn =>
    btn.addEventListener('click', () => {
      state.projection = btn.dataset.projection;
      $$('[data-projection]').forEach(b => b.classList.toggle('is-active', b === btn));
      if (state.result) render(state.result);
    })
  );

  window.addEventListener('resize', () => { if (state.result) render(state.result); });

  // ── 启动 ─────────────────────────────────────────────
  // 优先级：localStorage 手动保存 > 历史采集记录 > 系统默认
  initIdentity();

  (async () => {
    // 1. 先拉系统默认（不显示）
    const defaults = await fetchDefaults();

    // 2. 再尝试加载历史采集
    const hasHistory = await loadLastCapture();

    if (!hasHistory) {
      // 无历史时用系统默认填入所有字段
      if (defaults) {
        writeConfig(defaults);
        setStatus('✅ 默认参数已填入，请确认手眼矩阵和机器人位姿后点击「📡 采集真实点云」', 'success');
      } else {
        setStatus('请填写手眼矩阵和机器人位姿后，点击「📡 采集真实点云」开始测试', '');
      }
    }

    // 3. 始终把 localStorage 保存的矩阵和位姿覆盖回来（优先级最高）
    const savedMatrix = lsLoad(LS_MATRIX);
    if (savedMatrix) {
      writeMatrix(savedMatrix);
      // 在矩阵卡片显示提示
      showTip('matrix-save-tip', '🔁 已自动还原上次手动保存的手眼矩阵', 'saved');
    }
    const savedPose = lsLoad(LS_POSE);
    if (savedPose) {
      writeGroup('data-pose', savedPose);
      showTip('pose-save-tip', '🔁 已自动还原上次手动保存的机器人位姿', 'saved');
    }
  })();

}());
