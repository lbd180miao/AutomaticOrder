
(function () {
  const healthGrid = document.getElementById('device-health-grid');
  const healthSummary = document.getElementById('health-summary');
  const labels = {online:'在线', offline:'离线', checking:'检测中', unknown:'状态未知', disabled:'已禁用', unconfigured:'未配置', simulated:'模拟模式'};
  let healthRows = ['PLC', 'RVC 3D 相机', '海康 2D 相机'].map(name => ({name, state:'checking', detail:'等待首次检测', address:'—'}));
  const displayTime = value => value ? new Date(value).toLocaleString('zh-CN', {hour12:false}) : '—';
  const deviceMeta = [
    {icon: '/static/devices/icons/server.svg', type: '控制器'},
    {icon: '/static/devices/icons/device-projector.svg', type: '3D 视觉相机'},
    {icon: '/static/devices/icons/camera.svg', type: '2D 视觉相机'}
  ];
  function renderHealth() {
    // Keep disclosure nodes stable so polling preserves keyboard focus and open state.
    if (!healthGrid.children.length) {
      healthGrid.innerHTML = deviceMeta.map((meta, index) => `<article class="device-health-card">
        <details><summary>
          <span class="device-identity"><img class="device-icon" src="${meta.icon}" alt=""><span class="device-copy"><strong class="device-name"></strong><span>${meta.type}</span></span></span>
          <span class="device-state"></span>
          <span class="detail-label">查看详情<img src="/static/devices/icons/chevron-right.svg" alt=""></span>
        </summary>
        <div class="device-details"><p class="device-message"></p>
          <dl><div><dt>设备地址 / 序列号</dt><dd class="device-address"></dd></div><div><dt>最后检测</dt><dd class="device-checked"></dd></div><div><dt>最后在线</dt><dd class="device-last-online"></dd></div></dl>
          ${index === 0 ? `<section class="plc-listener-records"><h3>PLC 监听记录</h3>
          <p>各信号独立触发；本页监听记录每 48 小时全部清空。最多显示最近 200 条。</p>
          <p class="plc-log-state"></p><label>记录类型 <select id="plc-log-category"><option value="">全部</option><option value="2d">2D 监听</option><option value="3d">3D 监听</option><option value="mes">MES 请求</option><option value="rack">料框码监听</option><option value="connection">PLC 连接</option></select></label>
          <p>连接超时时，请在 AGV 电脑检查 PLC 地址、网卡路由及 TCP 102 端口；再核对 Rack/Slot 配置。</p>
          <pre id="plc-log-rows" style="max-height:360px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere" aria-live="polite">正在加载…</pre></section>` : ''}
          ${index === 2 ? '<p class="device-note">2D 相机在线仅表示设备可发现，不代表采集已验证。</p>' : ''}
        </div></details></article>`).join('');
    }
    healthRows.forEach((row, index) => {
      const card = healthGrid.children[index];
      card.dataset.state = row.state;
      card.querySelector('.device-name').textContent = row.name;
      card.querySelector('.device-state').textContent = labels[row.state] || '状态未知';
      card.querySelector('.device-message').textContent = row.detail;
      card.querySelector('.device-address').textContent = row.address || '—';
      card.querySelector('.device-checked').textContent = displayTime(row.checked_at);
      card.querySelector('.device-last-online').textContent = displayTime(row.last_online);
    });
  }
  async function pollHealth() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 6000);
    try {
      const response = await fetch('/devices/api/health/', {cache:'no-store', signal:controller.signal});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!Array.isArray(data.devices) || data.devices.length !== 3) throw new Error('状态数据不完整');
      healthRows = data.devices;
      healthSummary.textContent = `${healthRows.filter(row => row.state === 'online').length} / 3 台在线`;
    } catch (error) {
      healthRows = healthRows.map(row => ({...row, state:'unknown', detail:'监控接口无法访问，当前设备状态未知；请检查页面与服务器连接。'}));
      healthSummary.textContent = '监控连接中断，正在自动重试';
    } finally {
      clearTimeout(timeout);
      renderHealth();
      setTimeout(pollHealth, 2000);
    }
  }
  async function pollLogs() {
    const output = document.getElementById('plc-log-rows');
    try {
      const category = document.getElementById('plc-log-category').value;
      const response = await fetch('/devices/api/plc-logs/?category=' + encodeURIComponent(category), {cache:'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      const names = {'2d':'2D', '3d':'3D', mes:'MES', rack:'料框码', connection:'连接'};
      document.querySelector('.plc-log-state').textContent = (data.running ? '监听运行中' : '监听未运行') + '；下次清空：' + displayTime(data.next_clear_at);
      output.textContent = data.records.map(row => `${displayTime(row.created_at)} [${names[row.category] || row.category}] ${row.message}`).join('\n') || '暂无监听记录';
    } catch (error) { output.textContent = '监听记录加载失败：' + error.message; }
  }
  renderHealth();
  document.getElementById('plc-log-category').addEventListener('change', pollLogs);
  async function refreshLogs() { await pollLogs(); setTimeout(refreshLogs, 3000); }
  refreshLogs();
  pollHealth();
})();

