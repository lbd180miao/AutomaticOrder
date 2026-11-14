
(function () {
  const healthGrid = document.getElementById('device-health-grid');
  const healthSummary = document.getElementById('health-summary');
  const labels = {degraded:'离线', online:'在线', offline:'离线', checking:'检测中', unknown:'状态未知', disabled:'已禁用', unconfigured:'未配置', simulated:'模拟模式'};
  let healthRows = ['PLC', 'RVC 3D 相机', '海康 2D 相机', '外部电脑'].map(name => ({name, state:'checking', detail:'等待首次检测', address:'—'}));
  const displayTime = value => value ? new Date(value).toLocaleString('zh-CN', {hour12:false}) : '—';
  const deviceMeta = [
    {icon: '/static/devices/icons/server.svg', type: '控制器'},
    {icon: '/static/devices/icons/device-projector.svg', type: '3D 视觉相机'},
    {icon: '/static/devices/icons/camera.svg', type: '2D 视觉相机'},
    {icon: '/static/devices/icons/server.svg', type: 'HTTP 通信服务'}
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
          ${index === 0 ? `<section class="plc-listener-records"><div class="plc-listener-heading"><h3>PLC 监听记录</h3><button type="button" id="plc-debug-toggle" class="plc-debug-toggle" aria-pressed="false" disabled>调试监听：读取中</button></div><p id="plc-debug-note" role="status">正常 PLC 逻辑</p>
          <p class="plc-log-state"></p>
          <div id="plc-input-status"></div>
          <p class="device-note">五项监听：两个条码首次非空或变化时处理，三个触发信号仅 0→1 执行。</p>
          <h4>最近记录</h4><div id="plc-log-rows">正在加载…</div>
          <details class="plc-diagnostics"><summary>诊断详情</summary>
          <p>DB2 · 记录保留 48 小时。正常模式：三个 Bool 启动或重连先读取基线，仅实际 0→1 触发；条码仅首次有效值或变化时处理，空值/NoRead 不重置去重。</p>
          <pre id="plc-connection-logs"></pre></details></section>` : ''}
          ${index === 3 ? '<p class="device-note"><a href="/mes/communication/?configure=1">修改通信配置</a></p>' : ''}
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
      if (!Array.isArray(data.devices) || data.devices.length !== 4) throw new Error('状态数据不完整');
      healthRows = data.devices;
      healthSummary.textContent = `${healthRows.filter(row => row.state === 'online').length} / 4 台在线`;
    } catch (error) {
      healthRows = healthRows.map(row => ({...row, state:'unknown', detail:'监控接口无法访问，当前设备状态未知；请检查页面与服务器连接。'}));
      healthSummary.textContent = '监控连接中断，正在自动重试';
    } finally {
      clearTimeout(timeout);
      renderHealth();
      setTimeout(pollHealth, 2000);
    }
  }
  let debugEnabled = false;
  let debugChanging = false;
  let debugRevision = 0;
  function updateDebugButton(state) {
    if (debugChanging) return;
    debugEnabled = !!state.enabled;
    const button = document.getElementById('plc-debug-toggle');
    if (!button) return;
    button.disabled = false;
    button.setAttribute('aria-pressed', String(debugEnabled));
    button.textContent = debugEnabled ? '调试监听：开 · 点击恢复正常' : '调试监听：关';
    document.getElementById('plc-debug-note').textContent = debugEnabled
      ? '调试模式：有效信号保持期间，2D/3D、料框码、产品条码和封箱在每次完成后间隔2秒重复执行业务，包含真实 MES 请求。'
      : '正常 PLC 逻辑：一次高电平只执行一次。';
  }
  healthGrid.addEventListener('click', async event => {
    const button = event.target.closest('#plc-debug-toggle');
    if (!button || debugChanging) return;
    debugChanging = true; debugRevision += 1; button.disabled = true;
    try {
      const response = await fetch('/devices/api/plc-listener-debug/', {
        method:'POST', headers:{'X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value},
        body:new URLSearchParams({enabled:String(!debugEnabled)})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '切换失败');
      debugRevision += 1; debugChanging = false; updateDebugButton(data);
    } catch(error) {
      document.getElementById('plc-debug-note').textContent = error.message;
    } finally { debugChanging = false; button.disabled = false; }
  });
  async function pollLogs() {
    const output = document.getElementById('plc-log-rows');
    try {
      const revision = debugRevision;
      const response = await fetch('/devices/api/plc-logs/', {cache:'no-store'});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '查询失败');
      if (revision === debugRevision && data.debug) updateDebugButton(data.debug);
      const names = {'2d':'2D', '3d':'3D', mes:'MES', rack:'料框码', connection:'连接'};
      const waiting = data.auto_start ? '正在启动自动监听' : '外部电脑手动模式';
      document.querySelector('.plc-log-state').textContent = (data.running ? (data.inputs && data.inputs.error ? '连接异常 · 正在重连' : '监听中') : waiting);
      const inputs = [
        ['product_barcode', '当前产品条码', 'DB2.DBB0 · String[20]'],
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
