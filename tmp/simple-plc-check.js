
(function () {
  const healthGrid = document.getElementById('device-health-grid');
  const healthSummary = document.getElementById('health-summary');
  const labels = {degraded:'已连接，数据访问异常', online:'在线', offline:'离线', checking:'检测中', unknown:'状态未知', disabled:'已禁用', unconfigured:'未配置', simulated:'模拟模式'};
  let healthRows = ['PLC', 'RVC 3D 相机', '海康 2D 相机'].map(name => ({name, state:'checking', detail:'等待首次检测', address:'—'}));
  const displayTime = value => value ? new Date(value).toLocaleString('zh-CN', {hour12:false}) : '—';
  const deviceMeta = [
    {icon: '/check', type: '控制器'},
    {icon: '/check', type: '3D 视觉相机'},
    {icon: '/check', type: '2D 视觉相机'}
  ];
  function renderHealth() {
    // Keep disclosure nodes stable so polling preserves keyboard focus and open state.
    if (!healthGrid.children.length) {
      healthGrid.innerHTML = deviceMeta.map((meta, index) => `<article class="device-health-card">
        <details><summary>
          <span class="device-identity"><img class="device-icon" src="${meta.icon}" alt=""><span class="device-copy"><strong class="device-name"></strong><span>${meta.type}</span></span></span>
          <span class="device-state"></span>
          <span class="detail-label">查看详情<img src="/check" alt=""></span>
        </summary>
        <div class="device-details"><p class="device-message"></p>
          <dl><div><dt>设备地址 / 序列号</dt><dd class="device-address"></dd></div><div><dt>最后检测</dt><dd class="device-checked"></dd></div><div><dt>最后在线</dt><dd class="device-last-online"></dd></div></dl>
          ${index === 0 ? `<section class="plc-listener-records"><h3>PLC 监听记录</h3>
          <p class="plc-log-state"></p>
          <div id="plc-input-status"></div>
          <p class="device-note">料框码变化时读取；触发信号从 0 变为 1 时执行。</p>
          <h4>最近记录</h4><div id="plc-log-rows">正在加载…</div>
          <details class="plc-diagnostics"><summary>诊断详情</summary>
          <p>DB2 · 记录保留 48 小时。启动时为 1 的信号等待复位后再触发。</p>
          <pre id="plc-connection-logs"></pre></details></section>` : ''}
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
      const response = await fetch('/check', {cache:'no-store', signal:controller.signal});
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
      const category = '';
      const response = await fetch('/check?category=' + encodeURIComponent(category), {cache:'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      const names = {'2d':'2D', '3d':'3D', mes:'MES', rack:'料框码', connection:'连接'};
      const waiting = data.auto_start ? '正在启动自动监听' : '外部电脑手动模式';
      document.querySelector('.plc-log-state').textContent = (data.running ? (data.inputs && data.inputs.error ? '连接异常 · 正在重连' : '监听中') : waiting);
      const inputs = [
        ['rack_barcode', '料框码', 'DB2.DBB24 · String[20]'],
        ['position_trigger', '3D定位触发', 'DB2.DBX46.2 · Bool'],
        ['foam_trigger', '泡棉视觉检测触发', 'DB2.DBX46.3 · Bool'],
        ['boxing_trigger', 'MES封箱上传触发', 'DB2.DBX46.4 · Bool']
      ];
      const panel = document.getElementById('plc-input-status');
      panel.replaceChildren();
      const sample = data.inputs || {};
      const stale = !sample.checked_at || Date.now() - Date.parse(sample.checked_at) > 15000;
      inputs.forEach(([key, title, address]) => {
        const row = document.createElement('p');
        const value = (sample.values || {})[key];
        const state = !data.running ? waiting : sample.error ? '等待连接'
          : stale ? '正在连接，等待读取' : value ? '已读到信号：' + String(value) : '正在监听';
        [title, address, state].forEach(text => { const cell = document.createElement('span'); cell.textContent = text; row.appendChild(cell); });
        panel.appendChild(row);
      });
      output.replaceChildren();
      const records = data.records.filter(row => row.category !== 'connection').slice(0, 20);
      records.forEach(row => {
        const item = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = displayTime(row.created_at) + ' · ' + (names[row.category] || row.category) + ' · ' + row.message.slice(0, 70);
        const detail = document.createElement('p'); detail.textContent = row.message;
        item.append(summary, detail); output.appendChild(item);
      });
      if (!records.length) output.textContent = '暂无触发记录';
      document.getElementById('plc-connection-logs').textContent = data.records.filter(row => row.category === 'connection').slice(0, 10).map(row => displayTime(row.created_at) + ' ' + row.message).join('\n') || '暂无连接异常';
    } catch (error) { output.textContent = '监听记录加载失败：' + error.message; }
  }
  renderHealth();
  async function refreshLogs() { await pollLogs(); setTimeout(refreshLogs, 3000); }
  refreshLogs();
  pollHealth();
})();
