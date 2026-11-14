(function () {
  const form = document.getElementById('device-alarm-filter');
  const alarms = document.getElementById('device-alarm-rows');
  const feedback = document.getElementById('device-alarm-error');
  const names = {'2d':'2D', '3d':'3D', mes:'MES', rack:'料框码', connection:'连接'};
  const displayTime = value => value ? new Date(value).toLocaleString('zh-CN', {hour12:false}) : '—';
  let controller;
  let timer;
  async function refresh() {
    clearTimeout(timer);
    if (controller) controller.abort();
    const current = new AbortController();
    controller = current;
    const timeout = setTimeout(() => current.abort(), 10000);
    try {
      const params = new URLSearchParams(new FormData(form));
      const response = await fetch('/devices/api/plc-logs/?' + params.toString(), {cache:'no-store', signal:current.signal});
      const data = await response.json();
      if (controller !== current) return;
      if (!response.ok) throw new Error(data.error || '查询失败');
      feedback.textContent = '';
      const opened = new Set(Array.from(alarms.querySelectorAll('details[open]')).map(item => item.dataset.id));
      alarms.replaceChildren();
      (data.alarms || []).forEach(row => {
        const item = document.createElement('details');
        item.dataset.id = String(row.id);
        item.open = opened.has(String(row.id));
        const summary = document.createElement('summary');
        summary.textContent = displayTime(row.created_at) + ' · ' + (names[row.category] || row.category) + ' · ' + row.message.slice(0, 70);
        const detail = document.createElement('p');
        detail.textContent = row.message;
        item.append(summary, detail);
        alarms.appendChild(item);
      });
      if (!(data.alarms || []).length) alarms.textContent = '所选时间范围内暂无报警记录';
    } catch (error) {
      if (controller !== current) return;
      feedback.textContent = error.name === 'AbortError' ? '报警记录加载超时，正在重试' : '报警记录加载失败：' + error.message;
      alarms.replaceChildren();
    } finally {
      clearTimeout(timeout);
      if (controller === current) timer = setTimeout(refresh, 3000);
    }
  }
  form.addEventListener('submit', event => { event.preventDefault(); refresh(); });
  form.addEventListener('reset', () => { setTimeout(refresh, 0); });
  refresh();
})();
