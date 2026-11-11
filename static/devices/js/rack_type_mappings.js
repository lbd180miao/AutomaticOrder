(() => {
  const root = document.getElementById('mapping-library');
  const editor = document.getElementById('mapping-editor');
  const rows = document.getElementById('mapping-rows');
  const feedback = document.getElementById('mapping-feedback');
  const query = document.getElementById('mapping-query');
  let items = [];
  let pending = false;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  function report(message, error = false) { feedback.textContent = message; feedback.classList.toggle('is-error', error); }
  const layerCount = value => ({'两层':2, '三层':3, '五层':5}[value] ?? String(value || '').replace(/层$/, ''));
  function render() {
    const filtered = items.filter(row => row.pkg_type_code.toLowerCase().includes(query.value.trim().toLowerCase()));
    document.getElementById('mapping-count').textContent = `${filtered.length} 条映射`;
    rows.innerHTML = filtered.map(row => `<tr><td><strong>${escape(row.pkg_type_code)}</strong></td><td>${escape(layerCount(row.rack_type))}</td><td><code>${escape(row.plc_value ?? '未配置')}</code></td><td><span class="mapping-status ${row.enabled ? '' : 'is-disabled'}">${row.enabled ? '启用' : '停用'}</span></td><td class="mapping-row-actions"><button type="button" data-edit="${row.id}" aria-label="编辑 ${escape(row.pkg_type_code)}">编辑</button><button type="button" data-delete="${row.id}" class="mapping-delete" aria-label="删除 ${escape(row.pkg_type_code)}">删除</button></td></tr>`).join('') || '<tr><td colspan="5">暂无匹配的映射</td></tr>';
  }
  async function load() {
    const response = await fetch(root.dataset.api, {cache:'no-store'});
    if (!response.ok) throw new Error('映射库读取失败，请刷新重试');
    const data = await response.json();
    items = data.items;
    const standard = ['2LayerRack', '3LayerRack', '5LayerRack'];
    items.sort((a,b) => (standard.includes(a.pkg_type_code) ? standard.indexOf(a.pkg_type_code) : 4) - (standard.includes(b.pkg_type_code) ? standard.indexOf(b.pkg_type_code) : 4));
    document.getElementById('mapping-target').textContent = `${data.target} · ${data.data_type}`;
    render();
  }
  function openEditor(row) {
    if (pending) return;
    editor.reset();
    editor.elements.id.value = row?.id || '';
    editor.elements.pkg_type_code.value = row?.pkg_type_code || '';
    editor.elements.rack_type.value = row ? layerCount(row.rack_type) : '';
    editor.elements.plc_value.value = row?.plc_value ?? '';
    editor.elements.enabled.checked = row ? row.enabled : true;
    document.getElementById('mapping-editor-title').textContent = row ? '编辑映射' : '新增映射';
    editor.hidden = false;
    report('');
    editor.elements.pkg_type_code.focus();
  }
  async function mutate(body) {
    if (pending) return;
    pending = true;
    root.querySelectorAll('button').forEach(button => button.disabled = true);
    try {
      const response = await fetch(root.dataset.api, {method:'POST', body});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '保存失败');
      editor.hidden = true;
      report(body.get('action') === 'delete' ? '映射已删除' : '映射已保存');
      await load();
    } catch (error) { report(error.message, true); }
    finally { pending = false; root.querySelectorAll('button').forEach(button => button.disabled = false); }
  }
  document.getElementById('mapping-add').addEventListener('click', () => openEditor());
  document.getElementById('mapping-cancel').addEventListener('click', () => { editor.hidden = true; });
  query.addEventListener('input', render);
  editor.addEventListener('submit', event => { event.preventDefault(); mutate(new FormData(editor)); });
  rows.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || pending) return;
    const id = Number(button.dataset.edit || button.dataset.delete);
    const row = items.find(item => item.id === id);
    if (!row) return;
    if (button.dataset.edit) return openEditor(row);
    if (!window.confirm(`删除 ${row.pkg_type_code} 的映射？后续收到该编码将无法完成料框处理。`)) return;
    const body = new FormData();
    body.set('csrfmiddlewaretoken', editor.elements.csrfmiddlewaretoken.value);
    body.set('action', 'delete'); body.set('id', id);
    mutate(body);
  });
  load().catch(error => { report(error.message, true); rows.innerHTML = '<tr><td colspan="5">无法加载映射库</td></tr>'; });
})();
