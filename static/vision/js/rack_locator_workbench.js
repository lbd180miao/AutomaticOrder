/* Capture and package bridge for the point-cloud template workbench. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const config = window.rackLocatorConfig;
  let frame = {};
  const recipeId = () => $('recipe-select')?.value || '';
  function showFrame(data) {
    frame = {...data};
    const image = $('rl-depth-image');
    image.src = data.raw_rgb_image_url || data.preview_image_url || data.pointcloud_preview_url || '';
    $('btn-export-package').disabled = !frame.pointcloud_token;
    $('rl-status').textContent = '点云已载入，可以框选区域、保存模板或开始计算。';
  }
  const captureButton = $('btn-capture');
  const modeDialog = $('capture-mode-dialog');
  let confirmedCapture = false;

  async function updateMode(enabled) {
    const options = enabled === undefined ? {cache: 'no-store'} : {
      method: 'POST',
      headers: {'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value},
      body: new URLSearchParams({enabled: String(enabled)})
    };
    const response = await fetch(captureButton.dataset.debugUrl, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '无法确认 PLC 心跳状态');
    captureButton.style.background = data.enabled ? '#218447' : '#626971';
    captureButton.title = data.enabled ? '手动调试，PLC 心跳已停止' : '正常心跳模式';
  }

  captureButton.disabled = true;
  updateMode().catch(error => { $('rl-status').textContent = error.message; })
    .finally(() => { captureButton.disabled = false; });

  captureButton.addEventListener('click', event => {
    if (confirmedCapture) return;
    event.stopImmediatePropagation();
    modeDialog.showModal();
  }, true);

  async function chooseMode(enabled) {
    modeDialog.close();
    captureButton.disabled = true;
    try {
      await updateMode(enabled);
      if (enabled) {
        confirmedCapture = true;
        captureButton.disabled = false;
        captureButton.click();
      } else {
        $('rl-status').textContent = '已退出手动调试。';
      }
    } catch (error) {
      $('rl-status').textContent = error.message;
    } finally {
      if (!confirmedCapture) captureButton.disabled = false;
      confirmedCapture = false;
    }
  }

  $('capture-mode-yes').onclick = () => chooseMode(true);
  $('capture-mode-no').onclick = () => chooseMode(false);

  $('btn-capture').addEventListener('click', async () => {
    const button = $('btn-capture');
    button.disabled = true;
    frame = {};
    $('btn-export-package').disabled = true;
    $('rl-status').textContent = '正在采集相机点云…';
    try {
      const response = await fetch(config.captureUrl, {
        method: 'POST', headers: {'Content-Type': 'application/json',
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value},
        body: JSON.stringify({recipe_id: recipeId(), layer_no: Number($('layer-no').value || 1)})
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error?.message || data.error || '采集失败');
      showFrame(data.data || data);
    } catch (error) {
      $('rl-status').textContent = error.message;
    } finally { button.disabled = false; }
  });
  function selectRecipe() {
    const option = $('recipe-select')?.selectedOptions[0];
    if (!option) return;
    $('recipe-id').value = option.value;
    $('layer-no').value = option.dataset.layer || '1';
    $('selected-recipe-name').textContent = option.dataset.name || option.textContent;
    $('selected-recipe-rack-no').textContent = option.dataset.rackNo || '未设置';
    const url = new URL(location.href); url.searchParams.set('recipe_id', option.value);
    history.replaceState(history.state, '', url);
  }
  const requested = new URLSearchParams(location.search).get('recipe_id');
  if (requested && Array.from($('recipe-select')?.options || []).some(o => o.value === requested)) $('recipe-select').value = requested;
  $('recipe-select')?.addEventListener('change', selectRecipe);
  selectRecipe();
  let refreshing = false;
  async function refreshRecipes(selectedId, quiet = false) {
    if (refreshing) throw new Error('配方列表正在刷新，请稍后重试');
    refreshing = true;
    const select = $('recipe-select'), previous = select.value;
    try {
      const response = await fetch(config.recipesUrl, {cache: 'no-store'});
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '配方列表读取失败');
      const recipes = data.data.recipes;
      select.replaceChildren();
      for (const recipe of recipes) {
        const option = document.createElement('option');
        option.value = String(recipe.id);
        option.textContent = recipe.recipe_name + (recipe.enabled ? '' : '（已停用）');
        Object.assign(option.dataset, {layer: recipe.layer_no, name: recipe.recipe_name, rackNo: recipe.rack_type});
        select.appendChild(option);
      }
      const desired = String(selectedId ?? previous);
      if (recipes.some(recipe => String(recipe.id) === desired)) select.value = desired;
      else {
        const option = document.createElement('option');
        option.value = ''; option.textContent = recipes.length ? '请选择配方' : '暂无配方，请在视觉配方管理中创建或导入';
        select.prepend(option); select.value = '';
      }
      if (select.value !== previous) select.dispatchEvent(new Event('change'));
      else selectRecipe();
      if (!quiet) $('workbench-recipe-status').textContent = `已刷新，共 ${recipes.length} 个配方。停用配方可在工作台编辑，其启用状态保持不变。`;
    } catch (error) {
      $('workbench-recipe-status').textContent = `刷新失败：${error.message}`;
      throw error;
    } finally { refreshing = false; }
  }
  window.addEventListener('focus', () => { void refreshRecipes(undefined, true).catch(() => {}); });
  window.rackLocatorOfflineBridge = {
    snapshot: () => ({...frame, recipe_id: recipeId(), layer_no: Number($('layer-no').value || 1),
                      roi_config: frame.roi_config || {}}),
    load: showFrame,
    renderResult: result => window.dispatchEvent(new CustomEvent('rack-cloud-result', {detail: result})),
  };
})();
