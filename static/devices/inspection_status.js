(() => {
  const panel = document.getElementById('inspection-status');
  if (!panel) return;
  const labels = {online: '在线', offline: '离线', degraded: '离线', checking: '检测中', unknown: '状态未知', disabled: '已禁用', unconfigured: '未配置', simulated: '模拟模式'};
  function render(data) {
    panel.querySelectorAll('[data-device]').forEach(row => {
      const device = (data.devices || []).find(item => item.kind === row.dataset.device);
      const badge = row.querySelector('.connection-state');
      const state = ['checking', 'unknown'].includes(device?.state) ? 'offline' : (device?.state || 'offline');
      badge.dataset.state = state;
      badge.textContent = labels[state] || labels.unknown;
      row.title = device?.detail || '';
    });
    const inputs = data.inputs || {};
    panel.querySelectorAll('[data-point]').forEach(cell => {
      const value = inputs.fresh ? inputs.values?.[cell.dataset.point] : null;
      const isWorking = cell.dataset.point.startsWith('rack_working');
      const active = value === true || value === 1 || value === '1' || value === 'True' || value === 'true';
      const inactive = value === false || value === 0 || value === '0' || value === 'False' || value === 'false';
      cell.textContent = value == null || value === '' ? '—' : isWorking ? (active ? '是' : inactive ? '否' : '未知') : String(value);
      cell.classList.toggle('is-working', isWorking && active);
    });
  }
  async function poll() {
    try {
      {
        const response = await fetch(panel.dataset.url, {cache: 'no-store', signal: AbortSignal.timeout(3000)});
        if (!response.ok) throw new Error('HTTP ' + response.status);
        render(await response.json());
      }
    } catch (error) {
      render({});
    } finally {
      window.setTimeout(poll, 1000);
    }
  }
  poll();
})();
