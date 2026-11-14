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
    $('btn-refresh-recipes').disabled = true;
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
        option.value = ''; option.textContent = recipes.length ? '请选择配方' : '暂无配方，请导入 JSON 或新建';
        select.prepend(option); select.value = '';
      }
      if (select.value !== previous) select.dispatchEvent(new Event('change'));
      else selectRecipe();
      if (!quiet) $('workbench-recipe-status').textContent = `已刷新，共 ${recipes.length} 个配方。停用配方可在工作台编辑，其启用状态保持不变。`;
    } catch (error) {
      $('workbench-recipe-status').textContent = `刷新失败：${error.message}`;
      throw error;
    } finally { refreshing = false; $('btn-refresh-recipes').disabled = false; }
  }
  $('btn-refresh-recipes').addEventListener('click', () => { void refreshRecipes().catch(() => {}); });
  window.addEventListener('focus', () => { void refreshRecipes(undefined, true).catch(() => {}); });
  $('btn-import-workbench-recipe').addEventListener('click', () => $('workbench-recipe-file').click());
  $('workbench-recipe-file').addEventListener('change', async event => {
    const file = event.target.files[0]; event.target.value = '';
    if (!file) return;
    const status = $('workbench-recipe-status'), button = $('btn-import-workbench-recipe');
    button.disabled = true;
    let imported = null;
    try {
      if (file.size > 32 * 1024 * 1024) throw new Error('请选择不超过 32 MB 的配方 JSON');
      status.textContent = '正在导入 3D 配方…';
      const form = new FormData(); form.append('file', file);
      const response = await fetch(config.importRecipeUrl, {method: 'POST',
        headers: {'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value}, body: form});
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.error || '导入失败');
      imported = data;
      await refreshRecipes(data.id, true);
      status.textContent = `文件「${file.name}」已导入，当前配方为「${data.name}」。配方名称取自 JSON 内容。${(data.warnings || []).join('；')}`;
    } catch (error) {
      status.textContent = imported ? `「${imported.name}」已导入，但列表刷新失败，请点击“刷新配方”，不要重复导入。${error.message}` : `导入失败：${error.message}`;
    } finally { button.disabled = false; }
  });
  window.rackLocatorOfflineBridge = {
    snapshot: () => ({...frame, recipe_id: recipeId(), layer_no: Number($('layer-no').value || 1),
                      roi_config: frame.roi_config || {}}),
    load: showFrame,
    renderResult: result => window.dispatchEvent(new CustomEvent('rack-cloud-result', {detail: result})),
  };
})();
