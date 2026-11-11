document.querySelectorAll('.mes-api-form').forEach(form => {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button');
    const card = form.closest('.mes-api-card');
    const summary = card.querySelector('.mes-result-summary');
    const raw = card.querySelector('.mes-raw-response');
    const output = card.querySelector('.mes-card-result');
    const payload = {rack_code: form.elements.rack_code.value.trim()};
    if (form.elements.product_code) payload.product_code = form.elements.product_code.value.trim();
    if (!payload.rack_code || (form.elements.product_code && !payload.product_code)) {
      summary.textContent = '请填写完整的请求参数。'; summary.dataset.state = 'error'; return;
    }
    const label = button.textContent;
    button.disabled = true; button.textContent = '调用中…';
    summary.textContent = '正在等待 MES 返回…'; summary.dataset.state = 'loading'; raw.hidden = true;
    try {
      const response = await fetch(form.dataset.url, {method: 'POST', headers: {'Content-Type':'application/json', 'X-CSRFToken':form.elements.csrfmiddlewaretoken.value}, body:JSON.stringify({action:form.dataset.action,payload})});
      const data = await response.json();
      output.textContent = JSON.stringify(data, null, 2); raw.hidden = false;
      const success = response.ok && data.success;
      summary.dataset.state = success ? 'success' : 'error';
      summary.textContent = success ? '调用成功' : ('调用失败：' + (data.error || data.message || '请查看原始响应'));
      if (form.dataset.action === 'UPLOAD_BOXING_RESULT' && success) {
        summary.textContent = '上传成功 · 区位号：' + (data.bin_code || 'MES 未返回区位号');
      }
      if (form.dataset.action === 'GET_RACK_RECIPE') raw.open = true;
    } catch (error) { summary.dataset.state = 'error'; summary.textContent = '请求异常：' + error.message; }
    finally { button.disabled = false; button.textContent = label; }
  });
});

const editor = document.getElementById('binding-dialog');
const bindingForm = document.getElementById('binding-form');
const deletion = document.getElementById('binding-delete-dialog');
const deleteForm = document.getElementById('binding-delete-form');
let activeCellEditor = null;
document.querySelectorAll('.binding-rack, .binding-products, .binding-bin').forEach(cell => {
  cell.tabIndex = 0;
  cell.title = '双击编辑，回车保存，Esc 取消';
  const begin = () => {
    if (activeCellEditor) { activeCellEditor.focus(); return; }
    const row = cell.closest('tr');
    const editButton = row.querySelector('[data-edit]');
    const productsCell = row.querySelector('.binding-products');
    const products = Array.from(productsCell.querySelectorAll('div'), el => el.textContent);
    const field = cell.classList.contains('binding-rack') ? 'rack_code' : cell.classList.contains('binding-bin') ? 'bin_code' : 'product_codes';
    const values = {rack_code: editButton.dataset.rack, bin_code: editButton.dataset.bin, product_codes: products.join('\n')};
    const original = Array.from(cell.childNodes);
    const input = document.createElement(field === 'product_codes' ? 'textarea' : 'input');
    input.className = 'mes-inline-input';
    input.value = values[field];
    input.setAttribute('aria-label', {rack_code:'料框码', bin_code:'区位号', product_codes:'全部产品条码'}[field]);
    if (field === 'product_codes') input.rows = Math.max(3, Math.min(10, products.length + 1));
    else input.maxLength = field === 'rack_code' ? 64 : 128;
    const hint = document.createElement('small');
    hint.textContent = field === 'product_codes' ? '每行一个；Shift+回车换行，回车保存，Esc 取消' : '回车保存，Esc 取消';
    const status = document.createElement('p');
    status.className = 'mes-form-error';
    status.setAttribute('role', 'status');
    cell.replaceChildren(input, hint, status);
    activeCellEditor = input;
    const restore = () => { cell.replaceChildren(...original); activeCellEditor = null; cell.focus(); };
    input.addEventListener('keydown', async event => {
      if (event.isComposing || event.keyCode === 229) return;
      if (event.key === 'Escape' && !input.disabled) { event.preventDefault(); restore(); return; }
      if (event.key !== 'Enter' || event.shiftKey || input.disabled) return;
      event.preventDefault();
      values[field] = input.value;
      if (input.value === (field === 'product_codes' ? products.join('\n') : field === 'rack_code' ? editButton.dataset.rack : editButton.dataset.bin)) { restore(); return; }
      const body = new FormData();
      body.set('csrfmiddlewaretoken', bindingForm.elements.csrfmiddlewaretoken.value);
      body.set('operation', 'save'); body.set('id', editButton.dataset.edit);
      Object.entries(values).forEach(([key, value]) => body.set(key, value));
      input.disabled = true; status.textContent = '保存中…';
      try {
        const response = await fetch(bindingForm.action, {method:'POST', headers:{Accept:'application/json'}, body});
        if (response.status === 404) throw new Error('该记录已不存在，请刷新列表后重试。');
        const result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.error || '保存失败，请重试。');
        window.location.reload();
      } catch (error) { status.textContent = error.message; input.disabled = false; input.focus(); }
    });
    input.focus(); input.select();
  };
  cell.addEventListener('dblclick', begin);
  cell.addEventListener('keydown', event => {
    if (event.target === cell && (event.key === 'Enter' || event.key === 'F2')) { event.preventDefault(); begin(); }
  });
});
function openEditor(button) {
  if (activeCellEditor) { activeCellEditor.focus(); return; }
  bindingForm.reset();
  bindingForm.querySelector('.mes-form-error').textContent = '';
  bindingForm.elements.id.value = button ? button.dataset.edit : '';
  document.getElementById('binding-dialog-title').textContent = button ? '编辑绑定' : '新增绑定';
  if (button) {
    bindingForm.elements.rack_code.value = button.dataset.rack;
    bindingForm.elements.bin_code.value = button.dataset.bin;
    bindingForm.elements.product_codes.value = Array.from(button.closest('tr').querySelectorAll('.binding-products div'), el => el.textContent).join('\n');
  }
  editor.showModal(); bindingForm.elements.rack_code.focus();
}
document.getElementById('binding-add').addEventListener('click', () => openEditor(null));
document.querySelectorAll('[data-edit]').forEach(button => button.addEventListener('click', () => openEditor(button)));
document.querySelectorAll('[data-delete]').forEach(button => button.addEventListener('click', () => {
  deleteForm.elements.id.value = button.dataset.delete;
  deleteForm.querySelector('.mes-form-error').textContent = '';
  document.getElementById('binding-delete-rack').textContent = button.dataset.rack;
  deletion.showModal(); deletion.querySelector('[data-close]').focus();
}));
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
[bindingForm, deleteForm].forEach(form => form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('[type=submit]');
  const error = form.querySelector('.mes-form-error');
  error.textContent = ''; button.disabled = true;
  try {
    const response = await fetch(form.action, {method:'POST',headers:{Accept:'application/json'},body:new FormData(form)});
    if (response.status === 404) throw new Error('该记录已不存在，请刷新列表后重试。');
    const result = await response.json();
    if (!response.ok || !result.success) throw new Error(result.error || '保存失败，请重试。');
    window.location.reload();
  } catch (err) { error.textContent = err.message; button.disabled = false; }
}));
