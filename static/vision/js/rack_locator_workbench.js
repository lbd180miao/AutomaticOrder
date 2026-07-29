/* ============================================================
 *  3D 料架定位工作台 · 交互逻辑
 *  采集点云 → 画 ROI → 计算偏差 → 保存到数据库
 *  次级：按 POS/层号自动拍照计算 + 历史记录
 * ============================================================ */
(function () {
  const CFG = window.rackLocatorConfig || {};
  const $ = (id) => document.getElementById(id);
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

  // ── 配置完整性校验 ──────────────────────────────────────
  if (!window.rackLocatorConfig || !CFG.captureUrl) {
    console.error('[rack_locator_workbench] rackLocatorConfig 未定义或 captureUrl 缺失！请检查模板中的 <script> 是否有语法错误。');
  }

  // ── 工作台状态 ──────────────────────────────────────────
  const state = {
    token: null,         // 持久化点云 token
    roi: null,           // 真实图像像素 ROI {x,y,w,h}
    drawing: false,
    start: null,
    displayRoi: null,
    alignmentToken: null,
    lastResultId: null,
    lastResultOk: false,
    currentRecipe: null,
    pendingRoi: null,    // 待应用的 ROI（在采集点云前加载）
    lastResult: null,    // 最近一次计算结果，供离线数据包保存
    source: '',          // 最近一次点云数据源
    captureRecipeId: null,
    captureLayerNo: null,
    lastCalculation: null,
    // ── 画笔（多边形）模式 ──
    drawMode: 'rect',        // 'rect' | 'polygon'
    polyPoints: [],          // 绘制中的多边形顶点（display 坐标）
    polyDrawing: false,      // 是否正在添加多边形顶点
    polyMousePos: null,      // 鼠标当前位置（用于实时预览连线）
  };

  // ── 暴露设置 ROI 的接口供外部调用 ────────────────────────
  window.rackLocatorSetRoi = function(targetRoi) {
    if (!targetRoi) return;

    // 外部JS初始化完成时，将页面初始化阶段暂存的 tempPendingRoi 迁移进来
    if (window.tempPendingRoi) {
      state.pendingRoi = window.tempPendingRoi;
      window.tempPendingRoi = null;
      console.log('[rackLocatorSetRoi] 已将 tempPendingRoi 迁移到 state.pendingRoi');
    }

    if (state.token && image.style.display !== 'none') {
      // 直接委托 applyPixelRoi，它已正确处理矩形和多边形两种情况
      if (applyPixelRoi(targetRoi)) {
        const roiType = (targetRoi.polygon && targetRoi.polygon.length >= 3)
          ? `多边形(${targetRoi.polygon.length}点)`
          : `矩形(${targetRoi.w}×${targetRoi.h})`;
        setStatus(`已加载配方 ROI [${roiType}]，可直接点击「开始计算」。`);
        console.log('[rackLocatorSetRoi] ROI 已应用到画布', targetRoi);
      } else {
        state.pendingRoi = targetRoi;
        console.log('[rackLocatorSetRoi] applyPixelRoi 暂不可用，已存入 pendingRoi');
      }
    } else {
      // 还没有点云，存入待应用状态
      state.pendingRoi = targetRoi;
      console.log('[rackLocatorSetRoi] ROI 已存储，等待点云采集后应用');
    }
  };

  // ── 同步 ROI 到右侧结果图 ──────────────────────────────
  // NOTE: 右侧画布只在计算完成（renderResult）后更新，以保留上一次的计算结果。
  // 左侧画布用于实时绘制新的 ROI，右侧画布仅展示历史计算结果，两侧相互独立。
  function syncRoiToRightSide() {
    // 不再将当前 ROI 同步到右侧，右侧只由 renderResult() 更新。
    // 保留函数签名以避免破坏现有调用链，但直接 no-op。
    return;
  }


  // ── Loading 遮罩 ─────────────────────────────────────────
  function showLoading(msg) {
    if ($('rl-loading')) return;
    const el = document.createElement('div');
    el.id = 'rl-loading';
    el.innerHTML = `<div class="rl-loading-card"><div class="rl-spinner"></div><p>${msg || '处理中...'}</p></div>`;
    document.body.appendChild(el);
  }
  function hideLoading() { $('rl-loading')?.remove(); }

  async function postJson(url, body, method = 'POST') {
    if (!url || typeof url !== 'string' || !url.startsWith('/')) {
      throw new Error(`API URL 未正确配置 (值为: ${url})。请刷新页面重试，或检查浏览器控制台是否有JS语法错误。`);
    }
    const res = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify(body || {}),
    });
    
    // 检查响应的Content-Type
    const contentType = res.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      // 如果不是JSON响应，读取文本内容用于调试
      const text = await res.text();
      console.error('服务器返回非JSON响应:', {
        status: res.status,
        statusText: res.statusText,
        contentType: contentType,
        responseText: text.substring(0, 500) // 只记录前500字符
      });
      
      // 如果是4xx或5xx错误，提供更有用的错误信息
      if (!res.ok) {
        throw new Error(`服务器错误 (${res.status}): ${res.statusText}。可能是URL路径错误或权限问题。`);
      }
      
      throw new Error('服务器返回了HTML页面而不是JSON数据。请检查API URL配置是否正确。');
    }
    
    // 正常解析JSON
    return res.json();
  }

  function setStatus(text) { const n = $('rl-status'); if (n) n.textContent = text; }

  function apiPayload(data) {
    if (!data || !data.data) return data || {};
    if (typeof data.data === 'object' && !Array.isArray(data.data)) {
      return {
        success: data.success,
        error: data.error || '',
        ...data.data,
      };
    }
    return {
      success: data.success,
      error: data.error || '',
      data: data.data,
    };
  }

  function numberInput(id, fallback) {
    const node = $(id);
    const value = node ? Number(node.value) : NaN;
    return Number.isFinite(value) ? value : fallback;
  }

  function currentRackSide() {
    return $('rack-side')?.value || 'LEFT';
  }

  function currentLayerNo() {
    return numberInput('layer-no-select', numberInput('layer-no', 1));
  }

  function currentMode() {
    return $('locate-mode')?.value || 'local';
  }

  function currentLocateType() {
    const typeControl = $('locate-type');
    if (typeControl) {
      return typeControl.value || 'LAYER';
    }
    return String(currentMode()).toLowerCase() === 'global' ? 'GLOBAL' : 'LAYER';
  }

  function currentLayerIndex() {
    const indexControl = $('layer-index');
    if (indexControl) {
      return Number(indexControl.value) || 1;
    }
    return currentLocateType() === 'GLOBAL' ? 0 : currentLayerNo();
  }

  // 同步新旧控件
  function syncControls() {
    const locateType = currentLocateType();
    const layerIndex = currentLayerIndex();
    
    // 同步到旧控件
    if ($('locate-mode')) {
      $('locate-mode').value = locateType === 'GLOBAL' ? 'global' : 'local';
    }
    if ($('layer-no')) {
      $('layer-no').value = layerIndex;
    }
    if ($('layer-no-select')) {
      $('layer-no-select').value = layerIndex;
    }
    
    // 同步到新控件
    if ($('locate-type')) {
      $('locate-type').value = locateType;
    }
    if ($('layer-index')) {
      $('layer-index').value = layerIndex;
    }
  }

  function semanticPayload(extra) {
    return {
      locate_type: currentLocateType(),
      layer_index: currentLayerIndex(),
      layer_no: currentLayerIndex(),
      ...(extra || {}),
    };
  }

  function setButton(id, enabled) {
    const node = $(id);
    if (node) node.disabled = !enabled;
  }

  function refreshActionState() {
    setButton('btn-capture', true);
    setButton('btn-redraw', Boolean(state.token));
    setButton('btn-polygon', Boolean(state.token));
    setButton('btn-save-recipe', Boolean(state.roi));
    setButton('btn-calculate', Boolean(state.token));
    setButton('btn-auto-align', Boolean(state.token));
    setButton('btn-save-roi', Boolean(state.alignmentToken));
    setButton('btn-write-plc', Boolean(state.lastResultId && state.lastResultOk));
    setButton('btn-export-package', Boolean(state.token));
  }

  async function refreshCurrentRecipe() {
    if (!CFG.currentRecipeUrl) return;
    try {
      const query = new URLSearchParams({
        locate_type: currentLocateType(),
        layer_index: String(currentLayerIndex()),
      });
      const res = await fetch(`${CFG.currentRecipeUrl}?${query.toString()}`);
      const data = apiPayload(await res.json());
      const recipe = data.recipe || null;
      state.currentRecipe = recipe;
      if (recipe && recipe.id && $('recipe-id')) {
        $('recipe-id').value = recipe.id;
      }
    } catch (e) {
      state.currentRecipe = null;
    }
  }

  function currentRoi3D() {
    return {
      x_min: numberInput('roi-x-min', -100),
      x_max: numberInput('roi-x-max', 100),
      y_min: numberInput('roi-y-min', -100),
      y_max: numberInput('roi-y-max', 100),
      z_min: numberInput('roi-z-min', -100),
      z_max: numberInput('roi-z-max', 100),
    };
  }

  // ── 选中配方的参数（标准坐标） ───────────
  // 新方案：配方选择改为卡片点击，数据存放在 .rl-recipe-card.selected 的 dataset 上
  function selectedCardData() {
    const card = document.querySelector('.rl-recipe-card.selected');
    return card ? card.dataset : null;
  }
  function currentRecipeData() {
    // 优先从下拉框读取（新版 UI）
    const select = document.getElementById('recipe-select');
    if (select && select.selectedIndex >= 0) {
      const option = select.options[select.selectedIndex];
      if (option && option.value) {
        return {
          standard_x: Number(option.dataset.sx || 0),
          standard_y: Number(option.dataset.sy || 0),
          standard_z: Number(option.dataset.sz || 0),
          layer_no: Number(option.dataset.layer || 1),
          position_no: Number(option.dataset.pos || 1),
          locate_type: currentLocateType(),
          layer_index: currentLayerIndex()
        };
      }
    }

    // 回退到旧的卡片读取方式
    const d = selectedCardData();
    const data = { layer_no: currentLayerIndex(), locate_type: currentLocateType(), layer_index: currentLayerIndex() };
    if (d) {
      data.standard_x = Number(d.sx || 0);
      data.standard_y = Number(d.sy || 0);
      data.standard_z = Number(d.sz || 0);
    }
    return data;
  }



  // ── 自动加载并显示配方 ROI ─────────────────────────────
  function normalizePixelRoi(targetRoi) {
    if (!targetRoi) return null;
    const roi = {
      x: Number(targetRoi.x),
      y: Number(targetRoi.y),
      w: Number(targetRoi.w),
      h: Number(targetRoi.h),
      feature_type: targetRoi.feature_type || 'rack_reference',
    };
    if (![roi.x, roi.y, roi.w, roi.h].every(Number.isFinite) || roi.w <= 0 || roi.h <= 0) {
      return null;
    }
    // 保留多边形顶点（不能丢弃！）
    if (targetRoi.polygon && Array.isArray(targetRoi.polygon) && targetRoi.polygon.length >= 3) {
      roi.polygon = targetRoi.polygon;
    }
    return roi;
  }

  function applyPixelRoi(targetRoi) {
    const roi = normalizePixelRoi(targetRoi);
    if (!roi || !state.token || !image.src || image.style.display === 'none') return false;

    const nat = naturalDims();
    if (!nat.w || !nat.h || !canvas.width || !canvas.height) return false;

    state.roi = roi;

    // 如果保存的 ROI 包含多边形顶点，重建 displayPolygon
    if (targetRoi.polygon && Array.isArray(targetRoi.polygon) && targetRoi.polygon.length >= 3) {
      const scaleX = canvas.width / nat.w;
      const scaleY = canvas.height / nat.h;
      state.roi = {
        ...roi,
        polygon: targetRoi.polygon,
        displayPolygon: targetRoi.polygon.map(pt => ({
          x: pt.x * scaleX,
          y: pt.y * scaleY,
        })),
      };
      state.displayRoi = null;  // 多边形模式下不使用 displayRoi
    } else {
      state.displayRoi = {
        x: roi.x * canvas.width / nat.w,
        y: roi.y * canvas.height / nat.h,
        w: roi.w * canvas.width / nat.w,
        h: roi.h * canvas.height / nat.h,
      };
    }
    draw();
    setReadout();
    syncRoiToRightSide();
    setButton('btn-calculate', true);
    return true;
  }

  async function recipePixelRoi(recipeId) {
    if (!recipeId) return null;
    // 正确的 URL：使用 ?id= 查询参数，而不是路径参数（后者会 404）
    const res = await fetch(`/vision/api/vision/3d/recipes/?id=${encodeURIComponent(recipeId)}`);

    const contentType = res.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      console.error('recipePixelRoi returned non-JSON:', res.status);
      throw new Error(`读取3D配方失败，服务器返回非JSON (HTTP ${res.status})`);
    }

    if (!res.ok) throw new Error(`读取3D配方失败（HTTP ${res.status}）`);
    const data = apiPayload(await res.json());
    if (!data.success) throw new Error(data.error || '读取3D配方失败');
    // 后端返回 {success, recipes: [...], data: {recipes: [...]}}，取第一条
    const recipes = data.recipes || (data.data && data.data.recipes) || [];
    const recipe = recipes[0] || null;
    return normalizePixelRoi(recipe?.roi_config?.target_roi || recipe?.roi_info?.target_roi);
  }

  /** 在点云图像已经加载到画布后，应用数据包或3D配方中的2D ROI。 */
  async function autoLoadAndShowRecipeRoi({ recipeId, targetRoi, source = '配方' } = {}) {
    const token = state.token;
    if (!token || !image.src || image.style.display === 'none') return false;

    try {
      // 优先级：① 调用方直接传入的 targetRoi
      //         ② 用户切换配方时已存入 state.pendingRoi
      //         ③ 页面初始化时外部JS尚未加载导致暂存的 window.tempPendingRoi（兜底）
      //         ④ 远程拉取 recipePixelRoi(recipeId)
      const roi = normalizePixelRoi(targetRoi)
        || normalizePixelRoi(state.pendingRoi)
        || normalizePixelRoi(window.tempPendingRoi)
        || await recipePixelRoi(recipeId);
      // 等待接口期间如果又加载了另一帧，旧 ROI 不再覆盖新画布。
      if (state.token !== token) return false;
      if (!roi) {
        setStatus('点云已加载，但当前3D配方ROI无法投影到图像，请检查相机坐标ROI。');
        return false;
      }
      if (!applyPixelRoi(roi)) return false;

      state.pendingRoi = null;
      window.tempPendingRoi = null;
      setStatus(`${source}2D ROI 已自动显示 (${roi.w}×${roi.h})，可直接计算偏差。`);
      console.log(`[自动ROI] 已从${source}加载2D ROI`, roi);
      return true;
    } catch (e) {
      console.warn('[自动ROI] 加载失败：', e);
      setStatus('点云已加载，但3D配方ROI投影失败，请检查配方坐标。');
      return false;
    }
  }

  function afterPreviewLoaded(callback) {
    const expectedSrc = image.src;
    const run = () => {
      if (image.src !== expectedSrc || !image.naturalWidth) return;
      const schedule = window.requestAnimationFrame || ((fn) => setTimeout(fn, 0));
      schedule(() => {
        if (image.src !== expectedSrc) return;
        resizeCanvas();
        callback();
      });
    };
    if (image.complete && image.naturalWidth > 0) run();
    else image.addEventListener('load', run, { once: true });
  }

  // ── 画布 / ROI ───────────────────────────────────────────
  const image = $('rl-depth-image');
  const canvas = $('rl-canvas');
  const ctx = canvas.getContext('2d');

  function resizeCanvas() {
    const rect = image.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(rect.width));
    canvas.height = Math.max(1, Math.round(rect.height));
    draw();
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // ── 绘制多边形 ROI ──
    if (state.roi && state.roi.displayPolygon && state.roi.displayPolygon.length >= 2) {
      const poly = state.roi.displayPolygon; // display 坐标（对应画布像素）
      ctx.save();
      ctx.strokeStyle = '#a855f7';
      ctx.lineWidth = 3;
      ctx.setLineDash([6, 3]);
      ctx.beginPath();
      ctx.moveTo(poly[0].x, poly[0].y);
      for (let i = 1; i < poly.length; i++) ctx.lineTo(poly[i].x, poly[i].y);
      ctx.closePath();
      ctx.stroke();
      ctx.fillStyle = 'rgba(168,85,247,0.14)';
      ctx.fill();
      ctx.setLineDash([]);
      // 绘制顶点圆点
      poly.forEach((pt) => {
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#a855f7';
        ctx.fill();
      });
      ctx.fillStyle = '#a855f7';
      ctx.font = '14px sans-serif';
      ctx.fillText('✏ target ROI', poly[0].x + 8, Math.max(18, poly[0].y - 6));
      ctx.restore();
      return;
    }

    // ── 绘制正在描绘中的多边形（实时预览） ──
    if (state.polyDrawing && state.polyPoints.length > 0) {
      const pts = state.polyPoints;
      ctx.save();
      ctx.strokeStyle = '#a855f7';
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 3]);
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
      // 绘制预览连线到当前鼠标位置
      if (state.polyMousePos) ctx.lineTo(state.polyMousePos.x, state.polyMousePos.y);
      ctx.stroke();
      ctx.setLineDash([]);
      // 绘制顶点
      pts.forEach((pt, idx) => {
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, idx === 0 ? 6 : 4, 0, Math.PI * 2);
        ctx.fillStyle = idx === 0 ? '#f59e0b' : '#a855f7';
        ctx.fill();
      });
      ctx.restore();
      return;
    }

    // ── 绘制矩形 ROI（原有逻辑） ──
    const roi = state.displayRoi;
    if (!roi) return;
    ctx.save();
    ctx.strokeStyle = '#22c55e';
    ctx.lineWidth = 3;
    ctx.setLineDash([8, 4]);
    ctx.strokeRect(roi.x, roi.y, roi.w, roi.h);
    ctx.fillStyle = 'rgba(34,197,94,0.16)';
    ctx.fillRect(roi.x, roi.y, roi.w, roi.h);
    ctx.fillStyle = '#22c55e';
    ctx.font = '14px sans-serif';
    ctx.fillText('target ROI', roi.x + 8, Math.max(18, roi.y + 18));
    ctx.restore();
  }

  function pointerToCanvas(e) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(canvas.width, e.clientX - rect.left)),
      y: Math.max(0, Math.min(canvas.height, e.clientY - rect.top)),
    };
  }
  function naturalDims() {
    return {
      w: image.naturalWidth || Number(image.dataset.naturalWidth) || canvas.width,
      h: image.naturalHeight || Number(image.dataset.naturalHeight) || canvas.height,
    };
  }
  function displayToReal(d) {
    const n = naturalDims();
    const sx = n.w / canvas.width, sy = n.h / canvas.height;
    return { x: Math.round(d.x * sx), y: Math.round(d.y * sy), w: Math.round(d.w * sx), h: Math.round(d.h * sy) };
  }
  function setReadout() {
    const n = $('rl-roi-readout');
    if (!n) return;
    if (!state.roi) { n.textContent = state.drawMode === 'polygon' ? '✏️ 单击添加顶点，双击闭合' : '拖拽绘制 ROI'; return; }
    const r = state.roi;
    if (r.polygon && r.polygon.length > 0) {
      n.textContent = `多边形 ROI: ${r.polygon.length} 个顶点  包围盒 w=${r.w}  h=${r.h}`;
    } else {
      n.textContent = `ROI  x=${r.x}  y=${r.y}  w=${r.w}  h=${r.h}`;
    }
  }

  // ── 矩形拖拽绘制（原有模式） ────────────────────────────
  canvas.addEventListener('mousedown', (e) => {
    if (!state.token) return;
    if (state.drawMode === 'polygon') return;  // 多边形模式由 click 处理
    state.drawing = true;
    state.start = pointerToCanvas(e);
    state.displayRoi = { x: state.start.x, y: state.start.y, w: 0, h: 0 };
    draw();
  });
  canvas.addEventListener('mousemove', (e) => {
    if (state.drawMode === 'polygon') {
      // 多边形模式：实时更新预览连线
      if (state.polyDrawing) {
        state.polyMousePos = pointerToCanvas(e);
        draw();
      }
      return;
    }
    if (!state.drawing || !state.start) return;
    const c = pointerToCanvas(e);
    state.displayRoi = {
      x: Math.min(state.start.x, c.x), y: Math.min(state.start.y, c.y),
      w: Math.abs(c.x - state.start.x), h: Math.abs(c.y - state.start.y),
    };
    draw();
  });
  window.addEventListener('mouseup', () => {
    if (state.drawMode === 'polygon') return;  // 多边形模式不使用 mouseup
    if (!state.drawing || !state.displayRoi) return;
    state.drawing = false;
    state.start = null;
    if (state.displayRoi.w < 3 || state.displayRoi.h < 3) { state.displayRoi = null; draw(); return; }
    const real = displayToReal(state.displayRoi);
    state.roi = { x: real.x, y: real.y, w: real.w, h: real.h, feature_type: 'rack_reference' };
    setReadout();
    syncRoiToRightSide();
    refreshActionState();
    
    // 自动保存新坐标到配方中
    autoSaveRoiToRecipe();
  });

  // ── 多边形画笔模式 ────────────────────────────────────
  // 将 display 坐标多边形转为真实像素坐标
  function displayPolyToReal(displayPts) {
    const n = naturalDims();
    const sx = n.w / canvas.width, sy = n.h / canvas.height;
    return displayPts.map(pt => ({ x: Math.round(pt.x * sx), y: Math.round(pt.y * sy) }));
  }

  // 从多边形点集计算包围盒（real 坐标）
  function polyBoundingBox(realPts) {
    const xs = realPts.map(p => p.x), ys = realPts.map(p => p.y);
    const minX = Math.min(...xs), minY = Math.min(...ys);
    const maxX = Math.max(...xs), maxY = Math.max(...ys);
    return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
  }

  // 闭合多边形并保存到 state.roi
  function closePolygon() {
    const pts = state.polyPoints;
    if (pts.length < 3) {
      setStatus('多边形至少需要 3 个顶点，请继续添加。');
      return;
    }
    const realPts = displayPolyToReal(pts);
    const bbox = polyBoundingBox(realPts);
    state.roi = {
      ...bbox,
      polygon: realPts,
      displayPolygon: pts.map(p => ({ x: p.x, y: p.y })),
      feature_type: 'rack_reference',
    };
    state.polyPoints = [];
    state.polyDrawing = false;
    state.polyMousePos = null;
    draw();
    setReadout();
    syncRoiToRightSide();
    refreshActionState();
    autoSaveRoiToRecipe();
    setStatus(`✅ 多边形 ROI 已闭合（${realPts.length} 个顶点），正在自动保存...`);
  }

  // 单击：在多边形模式下添加顶点
  canvas.addEventListener('click', (e) => {
    if (!state.token || state.drawMode !== 'polygon') return;
    // 避免 dblclick 时触发两次 click
    if (e.detail >= 2) return;
    const pt = pointerToCanvas(e);
    if (!state.polyDrawing) {
      // 开始新多边形
      state.polyPoints = [pt];
      state.polyDrawing = true;
    } else {
      // 检查是否点击了起点（闭合）
      const first = state.polyPoints[0];
      const dist = Math.hypot(pt.x - first.x, pt.y - first.y);
      if (dist < 12 && state.polyPoints.length >= 3) {
        closePolygon();
      } else {
        state.polyPoints.push(pt);
      }
    }
    draw();
  });

  // 双击：闭合多边形
  canvas.addEventListener('dblclick', (e) => {
    if (!state.token || state.drawMode !== 'polygon') return;
    e.preventDefault();
    if (state.polyDrawing && state.polyPoints.length >= 3) {
      closePolygon();
    }
  });

  // 右键：删除最后一个顶点
  canvas.addEventListener('contextmenu', (e) => {
    if (state.drawMode !== 'polygon') return;
    e.preventDefault();
    if (state.polyPoints.length > 1) {
      state.polyPoints.pop();
      draw();
    } else if (state.polyPoints.length === 1) {
      state.polyPoints = [];
      state.polyDrawing = false;
      state.polyMousePos = null;
      draw();
    }
  });

  // ── 画笔模式切换按钮 ─────────────────────────────────
  function enterPolygonMode() {
    state.drawMode = 'polygon';
    state.polyPoints = [];
    state.polyDrawing = false;
    state.polyMousePos = null;
    state.drawing = false;     // 停止矩形绘制
    const btn = $('btn-polygon');
    if (btn) btn.classList.add('polygon-active');
    const stage = $('rl-stage');
    if (stage) stage.classList.add('polygon-mode');
    setReadout();
    setStatus('已进入画笔模式：在点云图上单击逐点绘制不规则 ROI，双击或点击起点闭合，右键撤销末点。');
  }

  function exitPolygonMode() {
    state.drawMode = 'rect';
    state.polyPoints = [];
    state.polyDrawing = false;
    state.polyMousePos = null;
    const btn = $('btn-polygon');
    if (btn) btn.classList.remove('polygon-active');
    const stage = $('rl-stage');
    if (stage) stage.classList.remove('polygon-mode');
    setReadout();
  }

  $('btn-polygon')?.addEventListener('click', () => {
    if (!state.token) { setStatus('请先采集点云。'); return; }
    if (state.drawMode === 'polygon') {
      exitPolygonMode();
      setStatus('已退出画笔模式，可拖拽绘制矩形 ROI。');
    } else {
      enterPolygonMode();
    }
  });

  // ── 保存配方按钮（手动保存当前 ROI 到配方）─────────────────
  $('btn-save-recipe')?.addEventListener('click', async () => {
    if (!state.roi) { setStatus('请先画好 ROI 再保存。'); return; }
    const btn = $('btn-save-recipe');
    const origText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '保存中...';
    await autoSaveRoiToRecipe();
    btn.textContent = origText;
    btn.disabled = false;
    refreshActionState();
  });

  // ── 采集点云 ─────────────────────────────────────────────
  $('btn-capture').addEventListener('click', async () => {
    showLoading('3D 相机采集中...');
    try {
      // 优先使用工作台专用端点
      const captureApiUrl = CFG.captureUrl || CFG.legacyCaptureUrl || '/vision/api/rack-location/workbench/capture/';
      console.log('[采集点云] 使用API端点:', captureApiUrl);
      
      const raw = await postJson(captureApiUrl, semanticPayload({
        recipe_id: $('recipe-id').value || null,
        rack_side: currentRackSide(),
      }));
      const data = apiPayload(raw);
      if (!data.success) { setStatus(data.error || '采集失败'); return; }
      state.token = data.pointcloud_token;
      state.source = data.source || '';
      state.captureRecipeId = $('recipe-id').value || null;
      state.captureLayerNo = currentLayerIndex();
      state.alignmentToken = null;
      state.lastResultId = null;
      state.lastResultOk = false;
      state.roi = null; state.displayRoi = null;
      const previewUrl = data.pointcloud_preview_url || data.preview_image_url;
      if (previewUrl) {
        const urlWithTime = previewUrl + '?t=' + Date.now();
        image.src = urlWithTime;
        // 右侧结果区保留上一次的计算结果图，不在采集时覆盖。
        // 右侧仅在 renderResult() 中由后端返回的 result_image_url 更新。
      }
      image.dataset.naturalWidth = data.image_width;
      image.dataset.naturalHeight = data.image_height;
      image.style.display = 'block';
      canvas.style.display = 'block';
      $('rl-placeholder').style.display = 'none';
      $('rl-roi-readout').style.display = 'block';
      $('rl-source').textContent = '数据源 ' + (data.source || '—');
      setReadout();
      // 右侧若尚无结果图，显示占位提示；若有上次结果图则保留不动。
      if (!$('rl-result-img').src || $('rl-result-img').style.display === 'none') {
        if ($('rl-result-ph')) $('rl-result-ph').style.display = 'block';
        $('rl-result-img').style.display = 'none';
      } else {
        // 在右侧标题徽章上提示右侧显示的是上一次结果
        const saveStatus = $('record-save-status');
        if (saveStatus && !saveStatus.textContent.includes('已自动保存')) {
          saveStatus.className = 'badge badge-muted';
          saveStatus.textContent = '右侧为上次结果，点击计算偏差后更新';
        }
      }
      
      // 点云图像真正加载完成后，再读取本次采集所用3D配方的2D ROI。
      if (data.roi_projection_error) console.warn('[自动ROI] 3D ROI投影提示：', data.roi_projection_error);
      afterPreviewLoaded(() => autoLoadAndShowRecipeRoi({
        recipeId: state.captureRecipeId,
        targetRoi: data.recipe_pixel_roi,
        source: data.recipe_pixel_roi ? '配方3D ROI' : '配方',
      }));
      
      if (data.source && data.source.indexOf('sample') === 0) {
        setStatus('⚠ 未取到真实相机数据，已回退模拟点云'
          + (data.fallback_reason ? '：' + data.fallback_reason : '（相机未连接）')
          + '。请检查相机连接后重试。');
      } else {
        setStatus('点云已采集，正在加载配方 ROI...');
      }
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); refreshActionState(); }
  });

  $('btn-redraw').addEventListener('click', () => {
    state.roi = null; state.displayRoi = null;
    state.alignmentToken = null;
    // 同时清除多边形状态
    state.polyPoints = [];
    state.polyDrawing = false;
    state.polyMousePos = null;
    // 退出画笔模式，回到矩形模式
    exitPolygonMode();
    draw(); setReadout();
    setStatus('请重新绘制 ROI（矩形：拖拽 · 不规则：点击「画笔」按钮）。');
    refreshActionState();
  });

  $('btn-auto-align')?.addEventListener('click', async () => {
    if (!state.token) { setStatus('请先采集点云。'); return; }
    showLoading('自动对齐料架坐标系...');
    try {
      const raw = await postJson(CFG.autoAlignUrl, semanticPayload({
        pointcloud_token: state.token,
        recipe_id: $('recipe-id')?.value || null,
      }));
      const data = apiPayload(raw);
      if (!data.success) { setStatus(data.error || '自动对齐失败'); return; }
      state.alignmentToken = data.aligned_pointcloud_token || state.token;
      setStatus('自动对齐完成，可以保存当前 3D ROI。');
    } catch (e) {
      setStatus('自动对齐失败：' + e.message);
    } finally {
      hideLoading();
      refreshActionState();
    }
  });

  $('btn-save-roi')?.addEventListener('click', async () => {
    if (!state.alignmentToken) { setStatus('请先执行自动对齐。'); return; }
    const roi = currentRoi3D();
    showLoading('保存 3D ROI...');
    try {
      const raw = await postJson(CFG.saveRoiUrl, semanticPayload({
        recipe_id: $('recipe-id')?.value || null,
        roi_name: currentLocateType() === 'GLOBAL' ? '全局 ROI' : `第 ${currentLayerIndex()} 层 ROI`,
        alignment_token: state.alignmentToken,
        aligned_pointcloud_token: state.alignmentToken,
        ...roi,
      }));
      const data = apiPayload(raw);
      setStatus(data.success ? '3D ROI 已保存并启用。' : (data.error || '保存 ROI 失败'));
    } catch (e) {
      setStatus('保存 ROI 失败：' + e.message);
    } finally {
      hideLoading();
      refreshActionState();
    }
  });

  $('btn-write-plc')?.addEventListener('click', async () => {
    if (!state.lastResultId || !state.lastResultOk) {
      setStatus('只有定位成功的结果才允许写入 PLC。');
      return;
    }
    showLoading('写入 PLC 补偿值...');
    try {
      const raw = await postJson(CFG.writePlcUrl, { result_id: state.lastResultId });
      const data = apiPayload(raw);
      setStatus(data.success ? 'PLC 补偿值写入成功。' : (data.error || 'PLC 写入失败'));
    } catch (e) {
      setStatus('PLC 写入失败：' + e.message);
    } finally {
      hideLoading();
      refreshActionState();
    }
  });

  async function fetchRecentResults() {
    if (!CFG.results3dUrl) return [];
    const query = new URLSearchParams({
      locate_type: currentLocateType(),
      layer_index: String(currentLayerIndex()),
    });
    const res = await fetch(`${CFG.results3dUrl}?${query.toString()}`);
    const data = apiPayload(await res.json());
    return data.results || [];
  }

  // btn-production-locate 已合并到》开始计算《，不再单独绑定。

  // ── 计算偏差 ─────────────────────────────────────────────
  $('btn-calculate').addEventListener('click', async () => {
    if (!state.token) { setStatus('请先采集点云。'); return; }
    showLoading('计算坐标偏差中...');
    try {
      // 优先使用工作台专用端点
      const calculateApiUrl = CFG.calculateUrl || CFG.legacyCalculateUrl || CFG.testLocateUrl || '/vision/api/rack-location/workbench/calculate/';
      console.log('[计算偏差] 使用API端点:', calculateApiUrl);

      // 构建干净的 target_roi（去掉 displayPolygon 等前端内部字段，不传给后端）
      const cleanTargetRoi = state.roi ? {
        x: state.roi.x,
        y: state.roi.y,
        w: state.roi.w,
        h: state.roi.h,
        feature_type: state.roi.feature_type || 'rack_reference',
        ...(state.roi.polygon ? { polygon: state.roi.polygon } : {}),
      } : null;

      const calculation = {
        pointcloud_token: state.token,
        roi: currentRoi3D(),
        roi_3d: currentRoi3D(),
        roi_config: { target_roi: cleanTargetRoi },
        rack_side: currentRackSide(),
        recipe_id: $('recipe-id').value || null,
        recipe_data: currentRecipeData(),
        save_record: true,
        auto_extract_corners: true,
        algorithm_version: 'RECTANGLE_CORNERS_AUTO_V2',
      };
      const raw = await postJson(calculateApiUrl, semanticPayload(calculation));
      const data = apiPayload(raw);
      if (!data.success) { setStatus(data.error || '计算失败'); return; }
      state.lastCalculation = calculation;
      state.lastResultId = data.result?.result_id || data.result?.id || null;
      renderResult(data.result);
      const saveStatus = $('record-save-status');
      if (saveStatus) {
        saveStatus.className = 'badge badge-ok';
        saveStatus.textContent = state.lastResultId
          ? `✅ 已自动保存记录 #${state.lastResultId}`
          : '✅ 已自动保存记录';
      }
      const lastTime = $('last-time');
      if (lastTime) {
        lastTime.textContent = '上次计算：' + new Date().toLocaleString('zh-CN', { hour12: false });
      }
      setStatus(data.result.locate_ok
        ? '计算完成：定位 OK，本次3D记录已自动保存。'
        : ('计算完成：定位 NG，本次3D记录已自动保存 · ' + (data.result.error_message || data.result.error_code || '')));
      
      // 计算完成后自动选中下一个配方
      selectNextRecipe();
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); }
  });

  // ── 自动保存 ROI 到配方 ──────────────────────────────────
  async function autoSaveRoiToRecipe() {
    const recipeId = $('recipe-id')?.value;
    if (!recipeId) { setStatus('未找到配方·请先选择配方'); return; }
    if (!state.roi) { setStatus('请先在画布上绘制 ROI 区域'); return; }

    setStatus('正在保存 ROI 到配方...');
    try {
      // 构建干净的 target_roi：去掉 displayPolygon 等前端内部字段
      const targetRoi = {
        x: state.roi.x,
        y: state.roi.y,
        w: state.roi.w,
        h: state.roi.h,
        feature_type: state.roi.feature_type || 'rack_reference',
      };
      if (state.roi.polygon && state.roi.polygon.length > 0) {
        targetRoi.polygon = state.roi.polygon;
      }

      // 直接发送包含 target_roi 的 roi_config，后端会 merge 到现有配置中
      const payload = {
        id: recipeId,
        roi_config: { target_roi: targetRoi },
      };

      const raw = await postJson('/vision/api/vision/3d/recipes/', semanticPayload(payload), 'PATCH');
      const data = apiPayload(raw);
      if (!data.success) { setStatus(data.error || '保存失败，请查看控制台'); return; }

      const roiType = state.roi.polygon ? `多边形（${state.roi.polygon.length} 点）` : '矩形';
      setStatus(`✅ ${roiType} ROI 已保存到配方，可点击「开始计算」。`);
    } catch (e) {
      setStatus('保存失败：' + e.message);
    }
  }

  // ── 自动选中下一个配方 ──────────────────────────────────
  function selectNextRecipe() {
    const select = document.getElementById('recipe-select');
    if (!select || select.options.length === 0) return;
    
    const currentIndex = select.selectedIndex;
    let nextIndex = currentIndex + 1;
    
    // 如果已经是最后一个，循环回到第一个
    if (nextIndex >= select.options.length) {
      nextIndex = 0;
    }
    
    // 跳过空选项（如果有的话）
    while (nextIndex < select.options.length && !select.options[nextIndex].value) {
      nextIndex++;
      if (nextIndex >= select.options.length) {
        nextIndex = 0;
        break;
      }
    }
    
    // 更新下拉框选择
    if (select.options[nextIndex] && select.options[nextIndex].value) {
      const fromName = select.options[currentIndex].text.trim();
      const toName = select.options[nextIndex].text.trim();
      
      select.selectedIndex = nextIndex;
      // 触发change事件以应用配方
      select.dispatchEvent(new Event('change'));
      
      console.log(`已自动选中下一个配方：${toName}`);
      
      // 显示提示信息
      const statusSpan = document.getElementById('recipe-switch-status');
      if (statusSpan) {
        statusSpan.textContent = `✅ 计算完成，已自动切换：${fromName} → ${toName}`;
        statusSpan.style.color = '#059669';
        statusSpan.style.fontWeight = '700';
        
        // 3秒后恢复原样
        setTimeout(() => {
          statusSpan.textContent = '';
        }, 3000);
      }
    }
  }

  // 计算接口会同步保存深度图、结果图和 ROI 快照，无需二次点击。

  // ── 渲染结果 ─────────────────────────────────────────────
  function renderResult(r) {
    state.lastResult = r || null;
    const ok = r.locate_ok ?? r.is_success;
    state.lastResultOk = Boolean(ok);
    const v = $('rl-verdict');
    v.className = 'rl-verdict ' + (ok ? 'ok' : 'fail');
    $('rl-verdict-icon').textContent = ok ? '✅' : '❌';
    $('rl-verdict-text').textContent = ok ? '定位 OK' : '定位 NG · 请核查';
    $('rl-verdict-sub').textContent = ok ? '计算完成' : (r.error_message || r.error_code || '计算异常');

    setOffset('x', r.final_offset_x ?? r.offset_x, null);
    setOffset('y', r.final_offset_y ?? r.offset_y, null);
    setOffset('z', r.final_offset_z ?? r.offset_z, null);
    setOffset('rz', r.final_offset_rz ?? r.offset_rz, null);

    const conf = Number(r.confidence || 0);
    const bar = $('conf-bar'), lab = $('conf-val');
    bar.style.width = Math.min(100, conf * 100) + '%';
    bar.className = 'rl-conf-fill ' + (conf >= 0.8 ? 'high' : conf >= 0.7 ? 'mid' : 'low');
    lab.textContent = (conf * 100).toFixed(1) + '%';

    if (r.result_image_url) {
      const resultImg = $('rl-result-img');
      resultImg.src = r.result_image_url + '?t=' + Date.now();
      resultImg.style.display = 'block';
      $('rl-result-ph').style.display = 'none';
      resultImg.onload = null;
    }

    const meta = r.result_data || {};
    const actX = Number(r.actual_x || 0);
    const actY = Number(r.actual_y || 0);
    const actZ = Number(r.actual_z || 0);
    
    // 更新标准值（从当前选中的配方中获取）
    const recipeData = currentRecipeData();
    if ($('d-sx')) $('d-sx').textContent = (recipeData.standard_x || 0).toFixed(2);
    if ($('d-sy')) $('d-sy').textContent = (recipeData.standard_y || 0).toFixed(2);
    if ($('d-sz')) $('d-sz').textContent = (recipeData.standard_z || 0).toFixed(2);

    // 更新实测值
    if ($('d-ax')) $('d-ax').textContent = actX.toFixed(2);
    if ($('d-ay')) $('d-ay').textContent = actY.toFixed(2);
    if ($('d-az')) $('d-az').textContent = actZ.toFixed(2);


    $('d-points').textContent = meta.valid_point_count ?? meta.point_count ?? '—';

    const rectangle = r.opening_rectangle || meta.opening_rectangle;
    const algorithmVersion = r.algorithm_version || meta.algorithm_version || 'MEDIAN_V1';
    const isRectangleAlgorithm = ['RECTANGLE_CORNERS_V2', 'RECTANGLE_CORNERS_AUTO_V2'].includes(algorithmVersion);
    if ($('rl-algorithm-note')) {
      $('rl-algorithm-note').textContent = algorithmVersion === 'RECTANGLE_CORNERS_AUTO_V2'
        ? '算法：ROI 深度四边自动提取 V2（P5 由 P1～P4 后端计算）'
        : algorithmVersion === 'RECTANGLE_CORNERS_V2'
          ? '算法：矩形四边拟合 V2（P5 由 P1～P4 后端计算）'
        : '算法：历史中位数 V1（该结果不包含 P1～P5）';
    }
    const isLocateOk = r.locate_ok !== false && (rectangle || {}).locate_ok !== false;
    // 即使定位失败（如偏差超限），只要提取到了五点数据就显示出来，方便用户排查问题
    if (rectangle && rectangle.points && rectangle.center) {
      ['p1', 'p2', 'p3', 'p4'].forEach((key) => {
        const point = rectangle.points[key] || {};
        ['x', 'y', 'z'].forEach((axis) => {
          const node = $('v2-' + key + '-' + axis);
          if (node) node.textContent = Number(point[axis]).toFixed(3);
        });
      });
      ['x', 'y', 'z'].forEach((axis) => {
        const node = $('v2-p5-' + axis);
        if (node) node.textContent = Number(rectangle.center[axis]).toFixed(3);
      });
      const geometry = rectangle.geometry || {};
      const quality = rectangle.quality || {};
      if ($('v2-width')) $('v2-width').textContent = Number(geometry.width_mm || 0).toFixed(3);
      if ($('v2-height')) $('v2-height').textContent = Number(geometry.height_mm || 0).toFixed(3);
      const metricText = (value) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(3);
      if ($('v2-plane-rmse')) $('v2-plane-rmse').textContent = metricText(quality.plane_rmse_mm);
      if ($('v2-rectangle-fit-rmse')) $('v2-rectangle-fit-rmse').textContent = metricText(quality.rectangle_fit_rmse_mm);
      if ($('v2-result-state')) {
        $('v2-result-state').textContent = rectangle.reference_mode === 'roi_auto_only'
          ? '已从当前 ROI 自动提取实体四边并拟合 P1～P4；P5 为四角派生中心。标准四点未配置，不影响五点输出。'
          : '已从当前 ROI 自动提取实体开口四角 P1～P4；P5 为后端根据四角计算的矩形中心。';
        $('v2-result-state').style.background = '#dcfce7';
        $('v2-result-state').style.color = '#166534';
      }
      $('rl-v2-detail').style.display = 'block';
    } else {
      ['p1', 'p2', 'p3', 'p4', 'p5'].forEach((key) => {
        ['x', 'y', 'z'].forEach((axis) => {
          const node = $('v2-' + key + '-' + axis);
          if (node) node.textContent = '—';
        });
      });
      ['v2-width', 'v2-height', 'v2-plane-rmse', 'v2-rectangle-fit-rmse'].forEach((id) => {
        if ($(id)) $(id).textContent = '—';
      });
      if ($('v2-result-state')) {
        let stateMsg;
        if (isRectangleAlgorithm) {
          const msg = r.error_message || r.error_code || '';
          // 检查是否包含线条数量提示
          const hMatch = msg.match(/水平线不足[（(]当前(\d+)/);
          const vMatch = msg.match(/垂直线不足[（(]当前(\d+)/);
          if (vMatch && parseInt(vMatch[1]) < 2) {
            stateMsg = `⚠ 左/右边缘检测失败（当前垂直线${vMatch[1]}条）\n💡 请重新画 ROI：确保框住料架开口的左立柱和右立柱，ROI 不能只是一个横条，需要同时包含四条边线。`;
          } else if (hMatch && parseInt(hMatch[1]) < 2) {
            stateMsg = `⚠ 上/下边缘检测失败（当前水平线${hMatch[1]}条）\n💡 请重新画 ROI：确保框住料架开口的上下横梁。`;
          } else {
            stateMsg = `⚠ 自动提取未得到五点：${msg || '请让 ROI 完整框住料架开口四边（上/下/左/右）'}`;
          }
        } else {
          stateMsg = '这是升级前保存的中位数 V1 历史结果，不包含 P1～P5。重新画 ROI 并点击「🎯 开始计算」即可生成。';
        }
        $('v2-result-state').textContent = stateMsg;
        $('v2-result-state').style.background = '#fef3c7';
        $('v2-result-state').style.color = '#92400e';
        $('v2-result-state').style.whiteSpace = 'pre-line';
      }
      $('rl-v2-detail').style.display = 'block';
    }

    $('rl-detail').style.display = 'flex';

    // 五点示意图
    const rectangle2 = r.opening_rectangle || (r.result_data || {}).opening_rectangle;
    if (rectangle2 && rectangle2.points && rectangle2.center) {
      drawV2Points(rectangle2);
    } else {
      const wrap = $('rl-v2-canvas-wrap');
      if (wrap) wrap.style.display = 'none';
    }

    refreshActionState();
  }

  // ── 在右侧结果图上叠加绘制当前 ROI 框 ─────────────────────
  function drawRoiOnResultCanvas() {
    const resultImg = $('rl-result-img');
    const overlayCanvas = $('rl-result-roi-canvas');
    if (!overlayCanvas || !resultImg || !state.roi) {
      if (overlayCanvas) overlayCanvas.style.display = 'none';
      return;
    }

    // 结果图的实际显示尺寸
    const imgRect = resultImg.getBoundingClientRect();
    const dispW = imgRect.width;
    const dispH = imgRect.height;
    if (!dispW || !dispH) { overlayCanvas.style.display = 'none'; return; }

    // 自然像素尺寸（结果图与点云图一般同尺寸，用图像自然宽高）
    const natW = resultImg.naturalWidth || dispW;
    const natH = resultImg.naturalHeight || dispH;

    // 设置 canvas 像素大小与 CSS 显示大小匹配
    overlayCanvas.width = Math.round(dispW);
    overlayCanvas.height = Math.round(dispH);
    overlayCanvas.style.display = 'block';

    const rctx = overlayCanvas.getContext('2d');
    rctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

    const scaleX = dispW / natW;
    const scaleY = dispH / natH;

    if (state.roi.polygon && state.roi.polygon.length >= 3) {
      // ── 多边形 ROI ──
      const pts = state.roi.polygon;
      rctx.save();
      rctx.strokeStyle = '#a855f7';
      rctx.lineWidth = 2.5;
      rctx.setLineDash([6, 3]);
      rctx.beginPath();
      rctx.moveTo(pts[0].x * scaleX, pts[0].y * scaleY);
      for (let i = 1; i < pts.length; i++) {
        rctx.lineTo(pts[i].x * scaleX, pts[i].y * scaleY);
      }
      rctx.closePath();
      rctx.stroke();
      rctx.fillStyle = 'rgba(168,85,247,0.14)';
      rctx.fill();
      rctx.setLineDash([]);
      // 顶点圆点
      pts.forEach((pt) => {
        rctx.beginPath();
        rctx.arc(pt.x * scaleX, pt.y * scaleY, 3, 0, Math.PI * 2);
        rctx.fillStyle = '#a855f7';
        rctx.fill();
      });
      // 标签
      rctx.fillStyle = '#a855f7';
      rctx.font = 'bold 13px sans-serif';
      rctx.fillText('✏ ROI', pts[0].x * scaleX + 6, Math.max(16, pts[0].y * scaleY - 4));
      rctx.restore();
    } else {
      // ── 矩形 ROI ──
      const rx = state.roi.x * scaleX;
      const ry = state.roi.y * scaleY;
      const rw = state.roi.w * scaleX;
      const rh = state.roi.h * scaleY;
      rctx.save();
      rctx.strokeStyle = '#22c55e';
      rctx.lineWidth = 2.5;
      rctx.setLineDash([8, 4]);
      rctx.strokeRect(rx, ry, rw, rh);
      rctx.fillStyle = 'rgba(34,197,94,0.12)';
      rctx.fillRect(rx, ry, rw, rh);
      rctx.setLineDash([]);
      rctx.fillStyle = '#22c55e';
      rctx.font = 'bold 13px sans-serif';
      rctx.fillText('target ROI', rx + 6, Math.max(16, ry + 16));
      rctx.restore();
    }
  }


  function setOffset(axis, val, limit) {
    const cell = $('cell-' + axis), el = $('off-' + axis);
    const num = parseFloat(val);
    el.textContent = isNaN(num) ? '—' : (num > 0 ? '+' : '') + num.toFixed(2);
    cell.classList.remove('positive', 'negative', 'zero', 'out');
    if (isNaN(num)) return;
    if (limit != null && Math.abs(num) > limit) cell.classList.add('out');
    else if (Math.abs(num) < 0.01) cell.classList.add('zero');
    else if (num > 0) cell.classList.add('positive');
    else cell.classList.add('negative');
  }


  // ── P1～P5 五点 Canvas 示意图 ──────────────────────────────
  function drawV2Points(rectangle) {
    const wrap = $('rl-v2-canvas-wrap');
    const cv = $('v2-points-canvas');
    if (!wrap || !cv) return;

    const pts = rectangle.points || {};
    const center = rectangle.center || {};
    const labeledPoints = [
      { key: 'p1', label: 'P1左上', x: Number(pts.p1?.x || 0), z: Number(pts.p1?.z || 0) },
      { key: 'p2', label: 'P2右上', x: Number(pts.p2?.x || 0), z: Number(pts.p2?.z || 0) },
      { key: 'p3', label: 'P3右下', x: Number(pts.p3?.x || 0), z: Number(pts.p3?.z || 0) },
      { key: 'p4', label: 'P4左下', x: Number(pts.p4?.x || 0), z: Number(pts.p4?.z || 0) },
      { key: 'p5', label: 'P5中心', x: Number(center?.x || 0), z: Number(center?.z || 0) },
    ];

    // 计算边界加边距
    const xs = labeledPoints.map((p) => p.x);
    const zs = labeledPoints.map((p) => p.z);
    const xMin = Math.min(...xs), xMax = Math.max(...xs);
    const zMin = Math.min(...zs), zMax = Math.max(...zs);
    const xRange = (xMax - xMin) || 1;
    const zRange = (zMax - zMin) || 1;
    const PAD = 48;

    // 设置 canvas 尺寸
    const W = cv.offsetWidth || 320;
    const H = Math.max(180, Math.round(W * zRange / xRange) + PAD * 2);
    cv.width = W;
    cv.height = H;
    const ctx2 = cv.getContext('2d');
    ctx2.clearRect(0, 0, W, H);

    // 坐标映射函数：mm → canvas像素
    const toCanvasX = (mmX) => PAD + ((mmX - xMin) / xRange) * (W - PAD * 2);
    // Z轴：小 z 在下，大 z 在上（翻转 Y轴）
    const toCanvasY = (mmZ) => H - PAD - ((mmZ - zMin) / zRange) * (H - PAD * 2);

    // 画矩形边框（P1→P2→P3→P4→P1）
    ctx2.save();
    ctx2.strokeStyle = '#22c55e';
    ctx2.lineWidth = 2;
    ctx2.setLineDash([6, 3]);
    ctx2.beginPath();
    ['p1', 'p2', 'p3', 'p4'].forEach((key, i) => {
      const p = labeledPoints.find((lp) => lp.key === key);
      if (i === 0) ctx2.moveTo(toCanvasX(p.x), toCanvasY(p.z));
      else ctx2.lineTo(toCanvasX(p.x), toCanvasY(p.z));
    });
    ctx2.closePath();
    ctx2.stroke();
    ctx2.restore();

    // 画对角线（P1-P3、P2-P4）
    ctx2.save();
    ctx2.strokeStyle = 'rgba(99,102,241,0.4)';
    ctx2.lineWidth = 1;
    ctx2.setLineDash([3, 4]);
    const p1c = labeledPoints.find((p) => p.key === 'p1');
    const p3c = labeledPoints.find((p) => p.key === 'p3');
    const p2c = labeledPoints.find((p) => p.key === 'p2');
    const p4c = labeledPoints.find((p) => p.key === 'p4');
    ctx2.beginPath();
    ctx2.moveTo(toCanvasX(p1c.x), toCanvasY(p1c.z));
    ctx2.lineTo(toCanvasX(p3c.x), toCanvasY(p3c.z));
    ctx2.moveTo(toCanvasX(p2c.x), toCanvasY(p2c.z));
    ctx2.lineTo(toCanvasX(p4c.x), toCanvasY(p4c.z));
    ctx2.stroke();
    ctx2.restore();

    // 画点 + 标签
    const colors = { p1: '#f59e0b', p2: '#f59e0b', p3: '#f59e0b', p4: '#f59e0b', p5: '#6366f1' };
    labeledPoints.forEach((p) => {
      const cx2 = toCanvasX(p.x);
      const cy = toCanvasY(p.z);
      const isCenter = p.key === 'p5';

      // 圆点
      ctx2.save();
      ctx2.fillStyle = colors[p.key];
      ctx2.beginPath();
      ctx2.arc(cx2, cy, isCenter ? 7 : 5, 0, Math.PI * 2);
      ctx2.fill();
      if (isCenter) {
        ctx2.strokeStyle = '#a5b4fc';
        ctx2.lineWidth = 1.5;
        ctx2.stroke();
      }
      ctx2.restore();

      // 标签文字
      ctx2.save();
      ctx2.fillStyle = '#e2e8f0';
      ctx2.font = `bold ${isCenter ? 11 : 10}px monospace`;
      const labelX = cx2 + (p.x >= (xMin + xMax) / 2 ? -52 : 10);
      const labelY = cy + (p.z >= (zMin + zMax) / 2 ? -10 : 16);
      ctx2.fillText(p.label, labelX, labelY);
      // XZ 数字
      ctx2.fillStyle = '#94a3b8';
      ctx2.font = '9px monospace';
      ctx2.fillText(`(${p.x.toFixed(1)}, ${p.z.toFixed(1)})`, labelX, labelY + 12);
      ctx2.restore();
    });

    wrap.style.display = 'block';
  }

  window.addEventListener('resize', resizeCanvas);
  image.addEventListener('load', resizeCanvas);

  // 新增离线数据包桥接层：仅暴露当前快照和“加载到画布”，不改变原工作台流程。
  window.rackLocatorOfflineBridge = {
    snapshot() {
      return {
        pointcloud_token: state.token,
        source: state.source,
        roi_config: {
          ...currentRoi3D(),
          target_roi: state.roi ? { ...state.roi } : null,
        },
        result: state.lastResult,
        recipe_id: state.captureRecipeId || $('recipe-id')?.value || null,
        layer_no: state.captureLayerNo || currentLayerIndex(),
      };
    },
    load(payload) {
      if (!payload || !payload.pointcloud_token) throw new Error('数据包未返回有效点云');
      state.token = payload.pointcloud_token;
      state.source = payload.source || 'offline_package';
      state.captureRecipeId = payload.metadata?.recipe?.recipe_id || $('recipe-id')?.value || null;
      state.captureLayerNo = payload.metadata?.layer?.layer_no || currentLayerIndex();
      state.lastResult = payload.result || null;
      state.roi = null;
      state.displayRoi = null;
      const previewUrl = payload.preview_image_url;
      if (previewUrl) {
        image.src = previewUrl + (previewUrl.includes('?') ? '&' : '?') + 't=' + Date.now();
        $('rl-result-img').src = image.src;
        $('rl-result-img').style.display = 'block';
        $('rl-result-ph').style.display = 'none';
      }
      image.dataset.naturalWidth = payload.image_width || 640;
      image.dataset.naturalHeight = payload.image_height || 480;
      image.style.display = 'block';
      canvas.style.display = 'block';
      $('rl-placeholder').style.display = 'none';
      $('rl-roi-readout').style.display = 'block';
      $('rl-source').textContent = '数据源 ' + state.source;
      $('rl-source').style.display = '';
      const roi = payload.roi_config || {};
      ['x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max'].forEach((key) => {
        const node = $('roi-' + key.replace('_', '-'));
        if (node && roi[key] != null) node.value = Number(roi[key]).toFixed(3);
      });

      // 数据包图像加载到画布后优先使用包内2D ROI；旧包没有时按包内配方回查。
      if (payload.roi_projection_error) console.warn('[自动ROI] 数据包3D ROI投影提示：', payload.roi_projection_error);
      const packageRoi = normalizePixelRoi(payload.recipe_pixel_roi)
        || normalizePixelRoi(payload.roi_config?.target_roi);
      afterPreviewLoaded(() => autoLoadAndShowRecipeRoi({
        recipeId: state.captureRecipeId,
        targetRoi: packageRoi,
        source: payload.recipe_pixel_roi ? '数据包3D ROI' : (packageRoi ? '数据包' : '配方'),
      }));

      if (payload.result) renderResult(payload.result);
      refreshActionState();
    },
    renderResult,
  };
  
  // 监听新旧控件变化并同步
  ['locate-mode', 'layer-no-select', 'layer-no', 'locate-type', 'layer-index'].forEach((id) => {
    $(id)?.addEventListener('change', async () => {
      syncControls();
      state.alignmentToken = null;
      state.lastResultId = null;
      state.lastResultOk = false;
      refreshActionState();
      await refreshCurrentRecipe();
    });
  });

  document.addEventListener('DOMContentLoaded', async () => {
    syncControls();
    refreshActionState();
    await refreshCurrentRecipe();
  });
  if (document.readyState !== 'loading') {
    syncControls();
    refreshActionState();
    refreshCurrentRecipe();
  }
}());
