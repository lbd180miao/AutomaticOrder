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
  window.rackLocatorOfflineBridge = {
    snapshot: () => ({...frame, recipe_id: recipeId(), layer_no: Number($('layer-no').value || 1),
                      roi_config: frame.roi_config || {}}),
    load: showFrame,
    renderResult: result => window.dispatchEvent(new CustomEvent('rack-cloud-result', {detail: result})),
  };
})();
