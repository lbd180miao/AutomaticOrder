/* 3D 料架定位离线数据包管理（独立扩展模块）。 */
(function () {
  'use strict';

  const CFG = window.rackLocatorConfig || {};
  const baseUrl = CFG.offlinePackagesUrl || '/vision/offline/packages/';
  const byId = (id) => document.getElementById(id);
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
  const state = { selectedName: null, selectedPackage: null };
  let refreshTimer, listVersion = 0, renderedList = null;

  let libraryQuery = '';
  function packageUrl(name, action) {
    return `${baseUrl}${encodeURIComponent(name)}/${action ? `${action}/` : ''}${libraryQuery}`;
  }

  function escapeHtml(value) {
    const node = document.createElement('div');
    node.textContent = value == null ? '' : String(value);
    return node.innerHTML.replace(/"/g, '&quot;');
  }

  async function request(url, options) {
    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      ...(options || {}),
    });
    const data = await response.json();
    if (!response.ok || data.success === false) throw new Error(data.error || `请求失败 (${response.status})`);
    return data;
  }

  function message(text, error) {
    const node = byId('offline-package-message');
    if (!node) return;
    node.textContent = text || '—';
    node.style.color = error ? 'var(--danger)' : 'var(--text-muted)';
  }

  function toast(text, error) {
    let node = byId('offline-package-toast');
    if (!node) {
      node = document.createElement('div');
      node.id = 'offline-package-toast';
      node.setAttribute('role', 'status');
      Object.assign(node.style, {
        position: 'fixed', right: '24px', bottom: '24px', zIndex: '9999',
        maxWidth: '420px', padding: '12px 16px', borderRadius: '9px',
        color: '#fff', boxShadow: '0 12px 35px rgba(0,0,0,.28)',
      });
      document.body.appendChild(node);
    }
    node.textContent = text;
    node.style.background = error ? '#dc2626' : '#059669';
    node.style.display = 'block';
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => { node.style.display = 'none'; }, 3500);
  }

  function setActions(enabled) {
    ['btn-load-package', 'btn-reprocess-package', 'btn-delete-package'].forEach((id) => {
      const node = byId(id);
      if (node) node.disabled = !enabled;
    });
  }

  function openModal(history) {
    libraryQuery = history ? '?library=history' : '';
    byId('packages-modal-title').textContent = history ? '历史数据包（pic1）' : '离线数据包管理';
    state.selectedName = state.selectedPackage = renderedList = null;
    byId('offline-package-list').replaceChildren();
    byId('offline-package-detail').textContent = '请从左侧选择一个数据包。';
    setActions(false);
    const modal = byId('packages-modal');
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    loadList();
  }

  function closeModal() {
    clearTimeout(refreshTimer);
    listVersion++;
    const modal = byId('packages-modal');
    modal.hidden = true;
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  async function loadList(automatic = false) {
    clearTimeout(refreshTimer);
    const version = ++listVersion;
    const list = byId('offline-package-list');
    if (!automatic) message('正在读取数据包列表…');
    try {
      const data = await request(baseUrl + libraryQuery, { cache: 'no-store' });
      if (version !== listVersion) return;
      const packages = data.packages || [];
      const signature = JSON.stringify(packages);
      if (renderedList !== signature) {
        if (state.selectedName && !packages.some(pkg => pkg.package_name === state.selectedName)) {
          state.selectedName = null;
          state.selectedPackage = null;
          setActions(false);
          byId('offline-package-detail').innerHTML = '<p class="rl-package-empty">请从左侧选择一个数据包。</p>';
        }
        renderList(packages);
      }
      if (!automatic || signature !== renderedList) message(`共 ${packages.length} 个数据包`);
      renderedList = signature;
    } catch (error) {
      if (version !== listVersion) return;
      if (!list.querySelector('.rl-package-item')) list.textContent = error.message;
      renderedList = null;
      message(error.message, true);
    } finally {
      if (version === listVersion && !byId('packages-modal').hidden) {
        refreshTimer = setTimeout(() => loadList(true), 5000);
      }
    }
  }

  function renderList(packages) {
    const list = byId('offline-package-list');
    if (!packages.length) {
      list.innerHTML = libraryQuery
        ? '<p class="rl-package-empty">暂无历史采集记录。手动保存的数据在「数据包管理」中。</p><button type="button" class="btn btn-secondary" id="offline-open-saved">查看已保存的数据包</button>'
        : '<p class="rl-package-empty">暂无已保存的数据包，可先采集点云并保存。</p>';
      byId('offline-open-saved')?.addEventListener('click', () => openModal(false));
      setActions(false);
      return;
    }
    list.innerHTML = packages.map((pkg) => {
      const isRaw = pkg.is_raw || pkg.source === 'raw_folder';
      const posInfo = (!isRaw && pkg.position_no !== '—' && pkg.position_no != null) 
        ? `<span>POS${escapeHtml(pkg.position_no)} · L${escapeHtml(pkg.layer_no)}</span>` 
        : '<span>原始数据</span>';
      return `
      <button type="button" class="rl-package-item${pkg.package_name === state.selectedName ? ' selected' : ''}${isRaw ? ' raw-package' : ''}" data-package-name="${escapeHtml(pkg.package_name)}">
        <img loading="lazy" src="${escapeHtml(pkg.preview_url)}" alt="数据包预览" onerror="this.style.display='none'">
        <span><strong title="${escapeHtml(pkg.package_name)}">${escapeHtml(pkg.package_name)}</strong>${isRaw ? '<span class="raw-badge">原始数据</span>' : `<span>${escapeHtml(pkg.recipe_name)}</span>${posInfo}`}<span>${escapeHtml(formatTime(pkg.created_at))} · ${pkg.has_result ? '已定位' : '未定位'}</span></span>
      </button>`;
    }).join('');
    list.querySelectorAll('[data-package-name]').forEach((node) => {
      node.addEventListener('click', () => selectPackage(node.dataset.packageName));
    });
  }

  async function selectPackage(name) {
    const source = libraryQuery;
    state.selectedName = name;
    state.selectedPackage = null;
    setActions(false);
    message('正在加载数据包详情…');
    try {
      const data = await request(packageUrl(name));
      if (source !== libraryQuery || state.selectedName !== name) return;
      state.selectedPackage = data.package;
      renderDetail(data.package);
      setActions(true);
      byId('offline-package-list').querySelectorAll('.rl-package-item').forEach((node) => {
        node.classList.toggle('selected', node.dataset.packageName === name);
      });
      message(`已选择 ${name}`);
    } catch (error) {
      message(error.message, true);
    }
  }

  function renderDetail(pkg) {
    const result = pkg.result || {};
    const isRaw = pkg.is_raw || pkg.source === 'raw_folder' || pkg.metadata?.is_raw;
    const metadata = pkg.metadata || {};
    
    byId('offline-package-detail').innerHTML = `
      <img src="${escapeHtml(pkg.preview_url)}" alt="${escapeHtml(pkg.package_name)} 预览" onerror="this.style.display='none'">
      <div class="rl-package-meta">
        ${isRaw ? '<div><small>类型</small><strong style="color:#0ea5e9;">原始数据包</strong></div>' : ''}
        <div><small>配方</small><strong>${escapeHtml(pkg.recipe_name)}</strong></div>
        ${!isRaw && pkg.position_no !== '—' && pkg.position_no != null ? `<div><small>位置 / 层</small><strong>POS${escapeHtml(pkg.position_no)} / L${escapeHtml(pkg.layer_no)}</strong></div>` : ''}
        <div><small>创建时间</small><strong>${escapeHtml(formatTime(pkg.created_at || metadata.created_at))}</strong></div>
        <div><small>点云数量</small><strong>${escapeHtml(pkg.point_count || metadata.point_count || '未知')}</strong></div>
        <div><small>数据源</small><strong>${escapeHtml(pkg.source || metadata.source || '—')}</strong></div>
        ${result.error_message || result.result?.errorMessage ? '<div><small>失败原因</small><strong>' + escapeHtml(result.error_message || result.result.errorMessage) + '</strong></div>' : ''}
        <div><small>定位结果</small><strong>${pkg.has_result ? `${result.locate_ok ?? result.is_success ? 'OK' : 'NG'} · ${(Number(result.confidence || 0) * 100).toFixed(1)}%` : isRaw ? '原始数据' : '尚未定位'}</strong></div>
      </div>`;
  }

  async function exportCurrent() {
    const bridge = window.rackLocatorOfflineBridge;
    const snapshot = bridge?.snapshot();
    if (!snapshot?.pointcloud_token) return toast('请先采集或加载点云。', true);
    if (!snapshot.recipe_id) return toast('请先选择配方。', true);
    const button = byId('btn-export-package');
    button.disabled = true;
    message('正在保存数据包…');
    toast('正在保存当前数据包…');
    try {
      const data = await request(baseUrl, {
        method: 'POST',
        body: JSON.stringify({ ...snapshot, manual_save: true }),
      });
      message(`数据包已保存：${data.package.package_name}`);
      toast(`数据包已保存：${data.package.package_name}`);
      if (!byId('packages-modal').hidden) await loadList();
    } catch (error) {
      message(error.message, true);
      toast(`保存失败：${error.message}`, true);
    } finally {
      button.disabled = !bridge?.snapshot()?.pointcloud_token;
    }
  }

  async function loadSelected() {
    if (!state.selectedName) return;
    setActions(false);
    message('正在加载数据到画布…');
    try {
      const recipeId = document.getElementById('recipe-select')?.value
                    || document.getElementById('recipe-id')?.value || null;
      const data = await request(packageUrl(state.selectedName, 'load'), { 
          method: 'POST', 
          body: JSON.stringify({ recipe_id: recipeId }) 
      });
      await window.rackLocatorOfflineBridge.load(data.package);
      closeModal();
      toast('数据包已载入画布，可框选 ROI 或点击「开始计算」。');
    } catch (error) {
      message(error.message, true);
    } finally {
      setActions(!!state.selectedName);
    }
  }

  async function reprocessSelected() {
    if (!state.selectedName) return;
    const snapshot = window.rackLocatorOfflineBridge?.snapshot() || {};
    const recipeId = snapshot.recipe_id || state.selectedPackage?.recipe_id;
    const layerNo = snapshot.layer_no || state.selectedPackage?.layer_no;
    if (!recipeId || !layerNo) return message('当前配方或层号无效。', true);
    message('正在使用离线点云重新定位…');
    try {
      const data = await request(packageUrl(state.selectedName, 'reprocess'), {
        method: 'POST',
        body: JSON.stringify({ recipe_id: recipeId, layer_no: layerNo, modified_roi: snapshot.roi_config,
          algorithm: 'cloud_center' }),
      });
      window.rackLocatorOfflineBridge?.renderResult(data.result);
      await selectPackage(state.selectedName);
      if (data.result.is_success === false) {
        message('重新定位失败：' + data.result.error_message, true);
      } else {
        message('重新定位完成。');
      }
    } catch (error) {
      message(error.message, true);
    }
  }

  async function deleteSelected() {
    if (!state.selectedName || !window.confirm(`确认删除数据包 ${state.selectedName}？此操作不可撤销。`)) return;
    try {
      await request(packageUrl(state.selectedName, 'delete'), { method: 'DELETE' });
      state.selectedName = null;
      state.selectedPackage = null;
      byId('offline-package-detail').innerHTML = '<p class="rl-package-empty">请从左侧选择一个数据包。</p>';
      setActions(false);
      message('数据包已删除。');
      await loadList();
    } catch (error) {
      message(error.message, true);
    }
  }

  function formatTime(value) {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
  }

  byId('btn-packages')?.addEventListener('click', () => openModal(false));
  byId('btn-history-frame')?.addEventListener('click', () => openModal(true));
  byId('btn-export-package')?.addEventListener('click', exportCurrent);
  byId('btn-refresh-packages')?.addEventListener('click', () => loadList());
  byId('btn-load-package')?.addEventListener('click', loadSelected);
  byId('btn-reprocess-package')?.addEventListener('click', reprocessSelected);
  byId('btn-delete-package')?.addEventListener('click', deleteSelected);
  document.querySelectorAll('[data-package-close]').forEach((node) => node.addEventListener('click', closeModal));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !byId('packages-modal')?.hidden) closeModal();
  });
}());
