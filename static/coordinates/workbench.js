(function () {
  'use strict';
  const root = document.getElementById('coordinate-workbench');
  if (!root) return;
  const $ = (selector) => root.querySelector(selector);
  const $$ = (selector) => Array.from(root.querySelectorAll(selector));
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const state = { saved: null, result: null, projection: 'xy', dirty: false };

  function number(input) {
    const value = Number(input.value);
    if (!Number.isFinite(value)) throw new Error('所有坐标字段都必须填写有限数值');
    return value;
  }

  function readDraft() {
    const matrix = Array.from({ length: 4 }, () => Array(4).fill(0));
    $$('[data-matrix-row]').forEach((input) => {
      matrix[Number(input.dataset.matrixRow)][Number(input.dataset.matrixCol)] = number(input);
    });
    const group = (attribute) => {
      const values = {};
      $$(`[${attribute}]`).forEach((input) => { values[input.getAttribute(attribute)] = number(input); });
      return values;
    };
    return {
      recipe_id: state.saved && state.saved.recipe_id,
      layer_no: Number($('#coordinate-layer').value),
      mode: state.saved ? state.saved.mode : 'MOCK',
      hand_eye_matrix: matrix,
      hand_eye_source: state.saved ? state.saved.hand_eye_source : 'MOCK 手动矩阵',
      robot_pose: group('data-pose'),
      theoretical: group('data-theoretical'),
      roi: group('data-roi'),
    };
  }

  function writeConfig(config) {
    $$('[data-matrix-row]').forEach((input) => {
      input.value = config.hand_eye_matrix[Number(input.dataset.matrixRow)][Number(input.dataset.matrixCol)];
    });
    const write = (attribute, values) => $$(`[${attribute}]`).forEach((input) => { input.value = values[input.getAttribute(attribute)]; });
    write('data-pose', config.robot_pose); write('data-theoretical', config.theoretical); write('data-roi', config.roi);
    $('#hand-eye-source').textContent = config.hand_eye_source;
    $('#coordinate-mode').textContent = `${config.mode} 调试模式`;
  }

  async function request(url, options) {
    const response = await fetch(url, options);
    const payload = await response.json();
    if (!response.ok || !payload.success) throw new Error(payload.error && payload.error.message || '坐标请求失败');
    return payload.data;
  }

  async function load() {
    setStatus('正在生成模拟点云并执行坐标转换…');
    try {
      const data = await request(`${root.dataset.workbenchUrl}?layer_no=${$('#coordinate-layer').value}`);
      state.saved = clone(data.config); state.result = data; writeConfig(data.config); render(data); setDirty(false);
      setStatus(`第 ${data.config.layer_no} 层转换完成，ROI 保留 ${data.point_counts.roi} 个点`, 'success');
    } catch (error) { setStatus(error.message, 'error'); }
  }

  async function post(url, draft) {
    return request(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': $('[name=csrfmiddlewaretoken]').value }, body: JSON.stringify(draft) });
  }

  async function preview() {
    try {
      const data = await post(root.dataset.previewUrl, readDraft()); state.result = data; render(data);
      setStatus(`草稿预览完成，ROI 保留 ${data.point_counts.roi} 个点；尚未保存`, 'success');
    } catch (error) { setStatus(error.message, 'error'); }
  }

  async function save() {
    try {
      const data = await post(root.dataset.saveUrl, readDraft()); state.saved = clone(data.config); state.result = data; writeConfig(data.config); render(data); setDirty(false);
      setStatus('坐标配置已保存，视觉定位链路下次运行即读取新值', 'success');
    } catch (error) { setStatus(error.message, 'error'); }
  }

  function render(data) {
    ['camera', 'base', 'roi'].forEach((name) => {
      $(`#${name}-count`).textContent = `${data.point_counts[name]} 点`;
      draw($(`#${name}-cloud`), data[`${name}_points`], name === 'roi' ? '#34d399' : name === 'base' ? '#38bdf8' : '#818cf8');
      const range = data.coordinate_ranges[name]; const second = state.projection === 'xy' ? 'y' : 'z';
      $(`#${name}-range`).textContent = `X ${fmt(range.x_min)} ～ ${fmt(range.x_max)} / ${second.toUpperCase()} ${fmt(range[`${second}_min`])} ～ ${fmt(range[`${second}_max`])} mm`;
    });
    ['x', 'y', 'z'].forEach((axis) => {
      $(`#result-${axis}-theoretical`).textContent = fmt(data.theoretical[axis]);
      $(`#result-${axis}-actual`).textContent = fmt(data.actual[axis]);
      $(`#result-${axis}-offset`).textContent = signed(data.offset[axis]);
    });
  }

  function draw(canvas, points, color) {
    const ratio = window.devicePixelRatio || 1; const width = canvas.clientWidth; const height = canvas.clientHeight;
    canvas.width = width * ratio; canvas.height = height * ratio; const ctx = canvas.getContext('2d'); ctx.scale(ratio, ratio); ctx.clearRect(0, 0, width, height);
    if (!points.length) return; const second = state.projection === 'xy' ? 1 : 2; const xs = points.map((p) => p[0]); const ys = points.map((p) => p[second]);
    let minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys); if (maxX === minX) maxX += 1; if (maxY === minY) maxY += 1;
    const pad = 18; ctx.strokeStyle = '#1e293b'; ctx.strokeRect(pad, pad, width - pad * 2, height - pad * 2); ctx.fillStyle = color;
    points.forEach((point) => { const x = pad + (point[0] - minX) / (maxX - minX) * (width - pad * 2); const y = height - pad - (point[second] - minY) / (maxY - minY) * (height - pad * 2); ctx.fillRect(x, y, 2, 2); });
  }

  function setDirty(value) { state.dirty = value; const el = $('#coordinate-dirty'); el.classList.toggle('is-saved', !value); el.textContent = value ? '有未保存修改' : '配置已保存'; }
  function setStatus(message, type) { const el = $('#coordinate-status'); el.textContent = message; el.className = `coordinate-status${type ? ` is-${type}` : ''}`; }
  function fmt(value) { return Number(value).toFixed(3); } function signed(value) { const n = Number(value); return `${n >= 0 ? '+' : ''}${n.toFixed(3)}`; }

  root.addEventListener('input', (event) => { if (event.target.matches('input')) setDirty(true); });
  $('#coordinate-layer').addEventListener('change', async (event) => { if (state.dirty && !window.confirm('当前修改尚未保存，确定切换层吗？')) { event.target.value = state.saved.layer_no; return; } await load(); });
  $('#preview-coordinate').addEventListener('click', preview); $('#save-coordinate').addEventListener('click', save);
  $('#restore-coordinate').addEventListener('click', () => { if (state.saved) { writeConfig(state.saved); setDirty(false); preview(); setStatus('已恢复后端最后保存的配置', 'success'); } });
  $$('[data-projection]').forEach((button) => button.addEventListener('click', () => { state.projection = button.dataset.projection; $$('[data-projection]').forEach((item) => item.classList.toggle('is-active', item === button)); if (state.result) render(state.result); }));
  window.addEventListener('beforeunload', (event) => { if (state.dirty) { event.preventDefault(); event.returnValue = ''; } });
  window.addEventListener('resize', () => { if (state.result) render(state.result); });
  load();
}());
