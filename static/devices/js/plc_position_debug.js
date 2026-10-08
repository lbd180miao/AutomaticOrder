(() => {
  const $ = id => document.getElementById(id);
  const recipe = $('position-recipe'), layer = $('position-layer');
  const start = $('position-start'), stop = $('position-stop'), status = $('position-status');
  const progress = $('position-progress');
  const url = $('plc-position-script').dataset.apiUrl;
  let token = null, timer = null, pending = false, stopping = false, lastCount = 0;

  recipe.addEventListener('change', () => {
    layer.max = recipe.selectedOptions[0].dataset.layers || 1;
    if (Number(layer.value) > Number(layer.max)) layer.value = 1;
  });

  function controls(running) {
    document.body.dataset.positionDebugRunning = running ? '1' : '';
    document.body.dataset.plcDebugRunning =
      document.body.dataset.positionDebugRunning || document.body.dataset.foamDebugRunning || '';
    start.disabled = running;
    stop.disabled = !running;
    recipe.disabled = running;
    layer.disabled = running;
    document.querySelector('#write-form button').disabled = Boolean(document.body.dataset.plcDebugRunning);
  }

  async function request(action, extra = {}) {
    const controller = new AbortController();
    const began = Date.now();
    const label = action === 'start' ? '正在检查PLC连接与触发位'
      : action === 'stop' ? '正在停止监听' : '正在读取PLC；若收到触发，将等待拍照及回写完成';
    const update = () => {
      const seconds = Math.floor((Date.now() - began) / 1000);
      progress.textContent = `${label} · 已等待 ${seconds} 秒`
        + (seconds >= 5 ? '。正在等待服务器响应；尚不能确认本次通信成功。' : '');
    };
    update();
    const ticker = setInterval(update, 1000);
    const timeout = setTimeout(() => controller.abort(), 120000);
    try {
      const response = await fetch(url, {
        method: 'POST', signal: controller.signal,
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value},
        body: JSON.stringify({action, token, ...extra}),
      });
      if (!response.ok) throw new Error(`服务器请求失败（HTTP ${response.status}）`);
      return await response.json();
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('请求超过120秒。后台采集可能仍在执行，请确认后重新监听。');
      throw error;
    } finally {
      clearInterval(ticker);
      clearTimeout(timeout);
    }
  }

  function finish(message, error = false) {
    clearTimeout(timer);
    token = null;
    stopping = false;
    controls(false);
    status.dataset.error = String(error);
    status.textContent = message;
    progress.textContent = '当前未监听；不会接收新的拍照触发。';
  }

  function display(data) {
    status.dataset.error = String(Boolean(data.error));
    const phase = data.phase === 'ARMING' ? '等待触发复位' : data.phase === 'WAIT_TRIGGER' ? '等待PLC触发'
      : data.phase === 'WAIT_RESET' ? '本次已处理，等待PLC复位' : data.phase;
    status.textContent = `${data.message}\n状态：${phase} · DB2.DBX46.2=${data.trigger ? 1 : 0}`
      + ` · 完成=${data.done ? 1 : 0} · 结果=${data.ok ? 'OK' : data.done ? 'NG' : '未完成'}`
      + (data.values ? `\n最近回写：X=${data.values.x}，Y=${data.values.y}，Z=${data.values.z}` : '')
      + (data.error ? '\n' + data.error : '');
    if (data.count > lastCount) {
      lastCount = data.count;
      const history = $('position-history');
      if (lastCount === 1) history.replaceChildren();
      const row = document.createElement('tr');
      [data.completed_at, data.count, ...['x', 'y', 'z'].map(axis => data.values ? Number(data.values[axis]).toFixed(3) : '—'),
        data.ok ? 'OK' : data.error || 'NG'].forEach(value => {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.appendChild(cell);
      });
      history.prepend(row);
      while (history.children.length > 30) history.lastElementChild.remove();
    }
  }

  async function poll() {
    if (!token || pending) return;
    pending = true;
    try {
      const data = await request(stopping ? 'stop' : 'poll');
      if (data.busy) {
        progress.textContent = data.error;
      } else if (!data.success) {
        finish('监听已停止：' + data.error, true);
        return;
      } else if (data.stopped) {
        finish(data.message);
        return;
      } else {
        display(data);
        progress.textContent = '最近一次通信完成：' + new Date().toLocaleTimeString();
      }
    } catch (error) {
      finish('停止发送扫描请求：' + error.message + '\n服务端当前请求结束后，未续期的监听会话将在15秒内到期。', true);
      return;
    } finally {
      pending = false;
    }
    if (token) timer = setTimeout(poll, stopping ? 0 : 500);
  }

  $('position-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (pending || token) return;
    pending = true;
    controls(true);
    stop.disabled = true;
    status.dataset.error = 'false';
    status.textContent = '正在检查PLC通信，验证通过后才启动监听…';
    try {
      let data = await request('start', {recipe_id: recipe.value, layer_no: layer.value});
      const deadline = Date.now() + 120000;
      while (data.busy && Date.now() < deadline) {
        progress.textContent = '另一路正在操作PLC，等待启动监听…';
        await new Promise(resolve => setTimeout(resolve, 500));
        data = await request('start', {recipe_id: recipe.value, layer_no: layer.value});
      }
      if (!data.success) throw new Error(data.error);
      token = data.token;
      lastCount = 0;
      stopping = false;
      display(data);
      controls(true);
    } catch (error) {
      finish(error.message, true);
    } finally {
      pending = false;
    }
    if (token) poll();
  });

  stop.addEventListener('click', () => {
    stopping = true;
    stop.disabled = true;
    status.textContent = pending ? '已请求停止，等待本次扫描或拍照回写结束…' : '正在停止监听…';
    if (!pending) {
      clearTimeout(timer);
      poll();
    }
  });
})();
