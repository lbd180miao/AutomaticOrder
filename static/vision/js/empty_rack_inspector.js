(function () {
  'use strict';

  const config = window.emptyRackInspectorConfig || {};
  const byId = id => document.getElementById(id);
  if (!byId('empty-rack-inspector')) return;

  const state = {recipe: null, imageFile: null, captureToken: '', sourceLabel: ''};

  function csrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
  }

  function setRecipeState(text, ready) {
    const target = byId('empty-run-recipe-state');
    target.textContent = text;
    target.classList.toggle('saved', Boolean(ready));
  }

  function showImage(url, label) {
    const image = byId('empty-run-preview');
    image.src = url;
    image.hidden = false;
    byId('empty-run-placeholder').style.display = 'none';
    byId('empty-run-image-meta').textContent = label;
  }

  async function loadRecipe() {
    try {
      const response = await fetch(config.recipeUrl);
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '读取配方失败');
      state.recipe = data.recipe || null;
      if (!state.recipe) {
        setRecipeState('没有已发布配方', false);
        byId('empty-run-inspect-btn').disabled = true;
        return;
      }
      const count = state.recipe.roi_config?.regions?.length || 0;
      setRecipeState(`${state.recipe.name} · ${count} 个 ROI`, true);
      byId('empty-run-inspect-btn').disabled = false;
    } catch (error) {
      setRecipeState(error.message, false);
      byId('empty-run-inspect-btn').disabled = true;
    }
  }

  async function useFile(file, label) {
    if (!file) return false;
    state.imageFile = file;
    state.captureToken = '';
    state.sourceLabel = label;
    const objectUrl = URL.createObjectURL(file);
    showImage(objectUrl, label);
    return true;
  }

  async function importRecordImage(file, record = {}) {
    return useFile(file, `泡棉检测记录 #${record.id || '-'} · POS ${record.pos ?? '-'}`);
  }

  byId('empty-run-upload-btn').addEventListener('click', () => byId('empty-run-file').click());
  byId('empty-run-file').addEventListener('change', event => {
    const file = event.target.files?.[0];
    if (file) useFile(file, file.name);
  });

  byId('empty-run-camera-btn').addEventListener('click', async () => {
    const button = byId('empty-run-camera-btn');
    button.disabled = true;
    button.textContent = '正在拍照…';
    try {
      const response = await fetch(config.cameraPreviewUrl, {
        method: 'POST',
        headers: {'X-CSRFToken': csrfToken(), 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'},
        body: new URLSearchParams({camera_code: config.cameraCode || 'CAM-INSPECT-RACK-01'}),
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '料架相机拍照失败');
      state.imageFile = null;
      state.captureToken = data.capture_token || '';
      state.sourceLabel = '料架相机拍照';
      showImage(`${data.image_url}?t=${Date.now()}`, `料架相机拍照 · ${data.image_width} × ${data.image_height}px`);
    } catch (error) {
      window.alert(error.message);
    } finally {
      button.disabled = false;
      button.textContent = '料架相机拍照';
    }
  });

  byId('empty-run-inspect-btn').addEventListener('click', async () => {
    if (!state.recipe) return window.alert('请先发布一份空箱检测配方。');
    if (!state.imageFile && !state.captureToken) return window.alert('请先获取或导入一张待检测图像。');
    const button = byId('empty-run-inspect-btn');
    const form = new FormData();
    form.append('recipe_id', state.recipe.id);
    if (state.imageFile) form.append('image', state.imageFile, state.imageFile.name);
    if (state.captureToken) form.append('preview_capture_token', state.captureToken);
    button.disabled = true;
    button.textContent = '检测中…';
    try {
      const response = await fetch(config.inspectUrl, {
        method: 'POST', headers: {'X-CSRFToken': csrfToken()}, body: form,
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '空箱检测失败');
      renderResult(data.result);
    } catch (error) {
      window.alert(error.message);
    } finally {
      button.disabled = false;
      button.textContent = '开始空箱检测';
    }
  });

  function renderResult(result) {
    const verdict = byId('empty-run-verdict');
    verdict.className = `empty-run-verdict ${result.is_empty ? 'pass' : 'fail'}`;
    verdict.innerHTML = result.is_empty
      ? `<strong>空箱 · OK</strong><span>${result.region_count} 个检测区域均未发现占用</span>`
      : `<strong>非空箱 · NG</strong><span>发现 ${result.occupied_count} 个疑似占用区域</span>`;
    byId('empty-run-result-time').textContent = new Date().toLocaleTimeString('zh-CN', {hour12:false});
    byId('empty-run-region-results').innerHTML = result.regions.map(region => `
      <div class="empty-run-region-row ${region.is_empty ? '' : 'ng'}">
        <div><strong>${escapeHtml(region.name)}</strong><small>泡棉占用 ${(region.foam_area_ratio * 100).toFixed(2)}% · 平均亮度 ${(region.mean_brightness * 100).toFixed(1)}%</small></div>
        <span class="empty-run-region-status">${region.is_empty ? '空 · OK' : '占用 · NG'}</span>
      </div>`).join('');
    if (result.result_image_url) showImage(`${result.result_image_url}?t=${Date.now()}`, `${state.sourceLabel || '检测图像'} · 已标注结果`);
  }

  function escapeHtml(value) {
    return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
  }

  window.EmptyRackInspector = {importRecordImage};
  loadRecipe();
})();
