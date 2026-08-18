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
    roiPlane1: null,     // Π1 顶部横梁 ROI
    roiPlane2: null,     // Π2 左侧立柱 ROI
    roiPlane3: null,     // Π3 底部横梁 ROI
    layerSpacingLine: null, // 层距测量线（真实图像像素坐标）
    pendingLayerSpacingLine: null,
    lineDrawing: false,
    lineStart: null,
    displayLayerSpacingLine: null,
    drawing: false,
    start: null,
    displayRoi: null,
    alignmentToken: null,
    lastResultId: null,
    lastResultOk: false,
    currentRecipe: null,
    pendingRoi: null,    // 待应用的 ROI（在采集点云前加载）
    pendingLocalTemplateRois: null,
    lastResult: null,    // 最近一次计算结果，供离线数据包保存
    source: '',          // 最近一次点云数据源
    captureRecipeId: null,
    captureLayerNo: null,
    pointcloudConsumed: false, // 每份点云只允许计算一次；再次计算必须重新采集
    lastResultRecipeId: null,
    lastCalculation: null,
    standardRackModel: null,
    standardRackCandidate: null,
    invalidRoiKeys: [],  // 最近一次结构校验失败所对应的 ROI
    localTemplateGeometryValid: null,
    recipeRequestSeq: 0,
    // ── 画笔（多边形）模式 ──
    drawMode: 'rect',        // 'rect' | 'polygon'
    polyPoints: [],          // 绘制中的多边形顶点（display 坐标）
    polyDrawing: false,      // 是否正在添加多边形顶点
    polyMousePos: null,      // 鼠标当前位置（用于实时预览连线）
  };
  let roiSaveChain = Promise.resolve();
  let roiSaveRequestSeq = 0;

  // ── 暴露设置 ROI 的接口供外部调用 ────────────────────────
  window.rackLocatorSetRoi = function(targetRoi, localTemplateRois, layerSpacingLine) {
    // 外部JS初始化完成时，将页面初始化阶段暂存的 tempPendingRoi 迁移进来
    if (window.tempPendingRoi) {
      state.pendingRoi = window.tempPendingRoi;
      window.tempPendingRoi = null;
      console.log('[rackLocatorSetRoi] 已将 tempPendingRoi 迁移到 state.pendingRoi');
    }
    if (window.tempPendingLocalTemplateRois) {
      state.pendingLocalTemplateRois = window.tempPendingLocalTemplateRois;
      window.tempPendingLocalTemplateRois = null;
    }
    if (window.tempPendingLayerSpacingLine) {
      state.pendingLayerSpacingLine = window.tempPendingLayerSpacingLine;
      window.tempPendingLayerSpacingLine = null;
    }

    const hasLocalTemplateRois = arguments.length >= 2;
    if (hasLocalTemplateRois) {
      if (state.token && image.style.display !== 'none') {
        applyLocalTemplateRois(localTemplateRois);
      } else {
        // 使用空对象表示“配方明确没有局部 ROI”，避免沿用上一配方的框。
        state.pendingLocalTemplateRois = localTemplateRois || {};
      }
    }
    if (arguments.length >= 3) {
      if (state.token && image.style.display !== 'none') {
        applyLayerSpacingLine(layerSpacingLine);
      } else {
        state.pendingLayerSpacingLine = layerSpacingLine || null;
      }
    }

    if (!targetRoi) {
      state.roi = null;
      state.displayRoi = null;
      state.pendingRoi = null;
      draw();
      setReadout();
      refreshActionState();
      return;
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

  window.rackLocatorRecipeChanged = function(recipeId) {
    state.roi = null;
    state.displayRoi = null;
    state.pendingRoi = null;
    state.pendingLocalTemplateRois = null;
    state.pendingLayerSpacingLine = null;
    clearLocalTemplateRois();
    clearLayerSpacingLine();
    state.currentRecipe = null;
    state.alignmentToken = null;
    draw();
    setReadout();
    renderLocalTemplate({});
    refreshActionState();
    // 配方下拉框是工作台的真实选择源，必须按精确 ID 同步标准模板。
    refreshCurrentRecipe(recipeId);
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

  function fmtNumber(value, digits = 3, signed = false) {
    const num = Number(value);
    if (!Number.isFinite(num)) return '—';
    const text = num.toFixed(digits);
    return signed && num > 0 ? `+${text}` : text;
  }

  function compensationOf(result) {
    const r = result || {};
    const meta = r.result_data || {};
    const plc = r.plc_payload || {};
    const comp = r.camera_rack_compensation
      || meta.camera_rack_compensation
      || r.rack_compensation
      || r.compensation_transform
      || meta.rack_compensation
      || meta.compensation_transform
      || plc.rack_compensation
      || null;
    if (!comp) return null;
    const matrix = r.compensation_matrix || comp.matrix || plc.compensation_matrix || null;
    const localCameraSource = ['local_template_3d', 'local_template_current_baseline'].includes(comp.source);
    const coordinateSystem = comp.coordinate_system
      || r.compensation_coordinate_system
      || meta.compensation_coordinate_system
      || plc.compensation_coordinate_system
      || (localCameraSource ? 'camera' : null);
    return { ...comp, coordinate_system: coordinateSystem, matrix };
  }

  function setCompText(id, value, digits = 3, signed = false) {
    const node = $(id);
    if (node) node.textContent = fmtNumber(value, digits, signed);
  }

  function poseFromMatrix(matrix) {
    if (!Array.isArray(matrix) || matrix.length !== 4) return null;
    const r00 = Number(matrix[0]?.[0]), r10 = Number(matrix[1]?.[0]);
    const r20 = Number(matrix[2]?.[0]), r21 = Number(matrix[2]?.[1]), r22 = Number(matrix[2]?.[2]);
    if (![r00, r10, r20, r21, r22].every(Number.isFinite)) return null;
    const sy = Math.sqrt(r00 * r00 + r10 * r10);
    const singular = sy < 1e-9;
    const rx = singular
      ? Math.atan2(-Number(matrix[1]?.[2] || 0), Number(matrix[1]?.[1] || 1))
      : Math.atan2(r21, r22);
    const ry = Math.atan2(-r20, sy);
    const rz = singular ? 0 : Math.atan2(r10, r00);
    const deg = 180 / Math.PI;
    return {
      x: Number(matrix[0]?.[3] || 0),
      y: Number(matrix[1]?.[3] || 0),
      z: Number(matrix[2]?.[3] || 0),
      rx: rx * deg,
      ry: ry * deg,
      rz: rz * deg,
    };
  }



  function localTemplateValidationMessage(templateValidation) {
    if (!templateValidation) return '';
    const failedChecks = (templateValidation.checks || [])
      .filter((check) => check && check.passed === false);
    const detail = failedChecks.map((check) => {
      const value = Number(check.value);
      const threshold = Number(check.threshold);
      const unit = check.unit || '';
      const digits = unit === '%' ? 1 : 2;
      const valueText = Number.isFinite(value) ? value.toFixed(digits) : '—';
      const thresholdText = Number.isFinite(threshold) ? threshold.toFixed(digits) : '—';
      const operator = unit === '%' ? '≥' : '≤';
      return `${check.name || '校验项'} ${valueText}${unit}（要求 ${operator}${thresholdText}${unit}）`;
    });
    const names = failedChecks.map((check) => String(check.name || '')).join(' ');
    const actions = [];
    if (/区域1|Π1|上水平面/.test(names)) {
      actions.push('Π1 缩小到一块连续的上层横梁平面，避开布料、边缘和背景');
    }
    if (/区域2|Π2|左竖直面/.test(names)) {
      actions.push('Π2 只框一块立柱侧平面，不要包含底板或横梁');
    }
    if (/区域3|Π3|下水平面/.test(names)) {
      actions.push('Π3 缩小到与 Π1 同类型、同朝向的下层横梁平面');
    }
    if (/平行/.test(names)) {
      actions.push('Π1/Π3 必须选择同一种表面；即使图像旋转了，也不能一个选侧面、另一个选正面');
    }
    if (/正交/.test(names)) {
      actions.push('Π2 应与 Π1/Π3 垂直，重新选择立柱的对应侧面');
    }
    const heading = String(templateValidation.message || '三平面质量提示')
      .replace(/^校验失败/, '质量提示');
    const lines = [heading];
    if (detail.length) lines.push(`实测：${detail.join('；')}`);
    if (actions.length) lines.push(`建议：${actions.join('；')}。直检模式不会因此停止计算或保存。`);
    return lines.join('\n');
  }

  function invalidRoiKeysFromValidation(templateValidation) {
    if (!templateValidation || templateValidation.is_valid !== false) return [];
    const names = (templateValidation.checks || [])
      .filter((check) => check && check.passed === false)
      .map((check) => String(check.name || ''));
    const keys = new Set();
    names.forEach((name) => {
      if (/区域1|Π1|上水平面/.test(name)) keys.add('roiPlane1');
      if (/区域2|Π2|左竖直面/.test(name)) keys.add('roiPlane2');
      if (/区域3|Π3|下水平面/.test(name)) keys.add('roiPlane3');
      if (/平行/.test(name)) {
        keys.add('roiPlane1');
        keys.add('roiPlane3');
      }
      if (/正交/.test(name)) keys.add('roiPlane2');
    });
    return [...keys];
  }

  function renderLocalTemplate(result) {
    // curTpl 可能在结果顶层(V2)，也可能在 result_data 内(V1)
    const curTpl = result?.local_template_cur
      || result?.result_data?.local_template_cur
      || null;
    const stdTpl = state.currentRecipe?.local_template_std || null;
    const templateValidation = result?.local_template_validation
      || result?.result_data?.local_template_validation
      || null;
    const standardValidation = result?.local_template_standard_validation
      || result?.result_data?.local_template_standard_validation
      || null;
    const qualityGateEnabled = Boolean(
      result?.quality_gate_enabled
      ?? result?.result_data?.quality_gate_enabled
      ?? false,
    );
    const invalidTemplate = qualityGateEnabled
      && Boolean(templateValidation && templateValidation.is_valid === false);
    const invalidStandard = qualityGateEnabled
      && Boolean(standardValidation && standardValidation.is_valid === false);
    state.invalidRoiKeys = qualityGateEnabled ? invalidRoiKeysFromValidation(templateValidation) : [];
    state.localTemplateGeometryValid = qualityGateEnabled
      ? (templateValidation ? templateValidation.is_valid === true : null)
      : (curTpl ? true : null);
    updateLocalTemplateRoiCount();
    draw();
    const status = $('template-status');
    const validationMessage = $('template-validation-message');
    const inlierComparison = result?.ransac_inlier_ratio_comparison
      || result?.result_data?.ransac_inlier_ratio_comparison
      || null;
    const fittedThreshold = Number(
      result?.ransac_distance_threshold_mm
      ?? result?.result_data?.ransac_distance_threshold_mm
      ?? selectedRansacThreshold(),
    );

    const btnSaveStd = $('btn-save-as-std');
    if (curTpl) {
      if (btnSaveStd) {
        btnSaveStd.style.display = 'inline-block';
        btnSaveStd.disabled = false;
        btnSaveStd.textContent = invalidTemplate ? '保存为标准模板（忽略质量提示）' : '保存为标准模板';
        // 暂存供保存按钮使用
        window._tempCurTpl = curTpl;
        window._tempCurTplValidation = templateValidation;
      }
    } else {
      if (btnSaveStd) btnSaveStd.style.display = 'none';
      window._tempCurTpl = null;
      window._tempCurTplValidation = null;
    }

    if (validationMessage && !qualityGateEnabled) {
      validationMessage.textContent = '';
      validationMessage.style.display = 'none';
    } else if (validationMessage) {
      if (invalidTemplate) {
        const standardHint = invalidStandard
          ? '\n标准模板：当前标准也有质量提示；直检模式允许继续计算或用本次结果覆盖。'
          : '';
        validationMessage.textContent = localTemplateValidationMessage(templateValidation) + standardHint;
        validationMessage.className = 'rl-template-validation-message warning';
        validationMessage.style.display = 'block';
      } else if (invalidStandard) {
        validationMessage.textContent = '现场三平面质量检查通过；当前标准模板有质量提示。直检模式仍允许计算，也可以用本次结果覆盖标准。';
        validationMessage.className = 'rl-template-validation-message warning';
        validationMessage.style.display = 'block';
      } else if (templateValidation) {
        validationMessage.textContent = '三平面结构校验通过，可以保存为标准模板。';
        validationMessage.className = 'rl-template-validation-message ok';
        validationMessage.style.display = 'block';
      } else {
        validationMessage.textContent = '';
        validationMessage.style.display = 'none';
      }
    }

    const comparisonPanel = $('ransac-inlier-comparison');
    if (comparisonPanel && inlierComparison) {
      comparisonPanel.style.display = 'block';
      const title = $('ransac-comparison-title');
      if (title) title.textContent = `内点率对比（本次正式拟合阈值 ${fittedThreshold.toFixed(1)} mm）`;
      ['1', '2', '3'].forEach((planeNo) => {
        ['2', '3', '5'].forEach((threshold) => {
          const ratio = Number(inlierComparison[`plane${planeNo}`]?.[threshold]);
          const node = $(`ransac-p${planeNo}-${threshold}`);
          if (node) node.textContent = Number.isFinite(ratio) ? `${(ratio * 100).toFixed(1)}%` : '—';
        });
      });
    } else if (comparisonPanel) {
      comparisonPanel.style.display = 'none';
    }

    if (!curTpl) {
      if (status) {
        status.textContent = '未计算现场模板';
        status.className = 'badge badge-muted';
      }
    } else if (!qualityGateEnabled) {
      if (status) {
        status.textContent = '已计算 · 直检';
        status.className = 'badge badge-ok';
      }
    } else if (invalidTemplate) {
      if (status) {
        status.textContent = '已计算 · 质量提示';
        status.className = 'badge badge-warning';
      }
    } else if (invalidStandard) {
      if (status) {
        status.textContent = '需重建标准';
        status.className = 'badge badge-warning';
      }
    } else if (!stdTpl) {
      if (status) {
        status.textContent = '无标准模板';
        status.className = 'badge badge-muted';
      }
    } else {
      if (status) {
        status.textContent = '匹配成功';
        status.className = 'badge badge-ok';
      }
    }

    function formatPlane(plane) {
      if (!plane) return '—';
      const normal = plane.normal || [0, 0, 0];
      const offset = plane.d ?? plane.offset;
      const d = Number.isFinite(Number(offset)) ? Number(offset).toFixed(2) : '0.00';
      const nx = normal[0].toFixed(3);
      const ny = normal[1].toFixed(3);
      const nz = normal[2].toFixed(3);
      return `N:[${nx}, ${ny}, ${nz}], D:${d}`;
    }

    const setHtml = (id, html) => {
      const node = $(id);
      if (node) node.innerHTML = html;
    };

    setHtml('tpl-std-p1', formatPlane(stdTpl?.plane1));
    setHtml('tpl-cur-p1', formatPlane(curTpl?.plane1));
    setHtml('tpl-std-p2', formatPlane(stdTpl?.plane2));
    setHtml('tpl-cur-p2', formatPlane(curTpl?.plane2));
    setHtml('tpl-std-p3', formatPlane(stdTpl?.plane3));
    setHtml('tpl-cur-p3', formatPlane(curTpl?.plane3));
  }

  function renderLayerSpacing(result) {
    const node = $('measured-layer-spacing');
    if (!node) return;
    const methodNode = $('layer-spacing-method');
    const rawValue = result?.measured_layer_spacing
      ?? result?.result_data?.measured_layer_spacing;
    const method = result?.layer_spacing_method
      || result?.result_data?.layer_spacing_method
      || '';
    const warning = result?.layer_spacing_warning
      || result?.result_data?.layer_spacing_warning
      || '';
    const value = Number(rawValue);
    node.textContent = rawValue !== null && rawValue !== undefined && Number.isFinite(value)
      ? `${value.toFixed(1)} mm`
      : '—';
    if (methodNode) {
      methodNode.textContent = warning
        ? warning
        : (method === 'endpoint_depth_cluster_3d_distance' ? '测量线 · 端点3D深度簇' : '三平面估算');
      methodNode.classList.toggle('warning', Boolean(warning));
    }
  }

  function renderCompensation(result) {
    const comp = compensationOf(result);
    const source = $('comp-source');
    if (!comp) {
      ['x', 'y', 'z', 'rx', 'ry', 'rz'].forEach((key) => {
        const node = $('comp-' + key);
        if (node) node.textContent = '—';
      });
      for (let row = 0; row < 4; row += 1) {
        for (let col = 0; col < 4; col += 1) {
          const node = $(`comp-m-${row}${col}`);
          if (node) node.textContent = '—';
        }
      }
      if (source) {
        source.className = 'badge badge-muted';
        source.textContent = '未计算';
      }
      return;
    }

    const pose = comp.pose6d || {
      ...(comp.translation_mm || {}),
      ...(comp.rotation_deg || {}),
    };
    setCompText('comp-x', pose.x, 3, true);
    setCompText('comp-y', pose.y, 3, true);
    setCompText('comp-z', pose.z, 3, true);
    setCompText('comp-rx', pose.rx, 4, true);
    setCompText('comp-ry', pose.ry, 4, true);
    setCompText('comp-rz', pose.rz, 4, true);

    const matrix = Array.isArray(comp.matrix) ? comp.matrix : [];
    for (let row = 0; row < 4; row += 1) {
      for (let col = 0; col < 4; col += 1) {
        const node = $(`comp-m-${row}${col}`);
        if (node) node.textContent = fmtNumber(matrix[row]?.[col], col === 3 ? 3 : 6, false);
      }
    }

    if ($('comp-formula')) {
      $('comp-formula').textContent = comp.placement_formula || '实际放件位姿 = T × 标准放件位姿';
    }
    if ($('comp-place-count')) {
      const robotCount = Number(comp.robot_taught_place_pose_count ?? 15);
      const visionCount = Number(comp.managed_place_pose_count ?? comp.vision_managed_place_pose_count ?? 0);
      $('comp-place-count').textContent = `机器人示教 ${robotCount} / 视觉管理 ${visionCount}`;
    }
    if (source) {
      const isCamera = comp.coordinate_system === 'camera';
      source.className = isCamera ? 'badge badge-ok' : 'badge badge-muted';
      source.textContent = isCamera ? '相机坐标系' : '坐标系未标注';
    }
  }

  function setRoiButtonMode(id, mode) {
    const node = $(id);
    if (!node) return;
    node.classList.remove('active', 'done');
    if (mode) node.classList.add(mode);
  }

  function updateFlowUI({ hasOkResult, hasCloud, canWritePlc } = {}) {
    if ($('flow-locate-text')) {
      $('flow-locate-text').textContent = hasOkResult
        ? '已生成 P1-P5 与整架补偿'
        : (hasCloud ? '已采集点云，可绘制 ROI 计算' : '匹配三钢架模型并计算当前料架位姿');
    }
    if ($('flow-plc-text')) {
      $('flow-plc-text').textContent = canWritePlc
        ? '可写入 PLC：机器人 15 点统一补偿'
        : '15 个放件点由机器人示教，视觉只输出补偿';
    }
  }

  function refreshActionState() {
    const canWritePlc = Boolean(state.lastResultId && state.lastResultOk);
    const canCalibrate = Boolean(
      state.lastResultId
      && state.lastResultRecipeId
      && state.lastResultOk
      && (state.lastResult?.opening_rectangle || state.lastResult?.result_data?.opening_rectangle)
    );
    const hasCloud = Boolean(state.token);
    setButton('btn-capture', true);
    setButton('btn-redraw', hasCloud);
    setButton('btn-polygon', hasCloud);
    const localRoisReady = hasAllLocalTemplateRois();
    const measurementSummary = updateMeasurementConfigProgress();
    setButton('btn-save-recipe', measurementSummary.count > 0);
    if ($('btn-save-recipe')) {
      $('btn-save-recipe').title = localRoisReady && state.localTemplateGeometryValid !== true
        ? '当前三平面有质量提示；直检模式允许保存'
        : '将外框、三平面与层距测量线保存到当前配方';
    }
    setButton('btn-calculate', hasCloud);
    setButton('btn-auto-align', hasCloud);
    setButton('btn-save-roi', Boolean(state.alignmentToken));
    setButton('btn-write-plc', canWritePlc);
    setButton('btn-export-package', hasCloud);
    // ROI 模式按鈕：采集点云后解锁
    setButton('btn-roi-target', hasCloud);
    setButton('btn-roi-plane1', hasCloud);
    setButton('btn-roi-plane2', hasCloud);
    setButton('btn-roi-plane3', hasCloud);
    setButton('btn-layer-spacing-line', hasCloud);
  }

  /** 更新「三平面已框选 x/3」计数徽章 */
  function updateLocalTemplateRoiCount() {
    const count = [state.roiPlane1, state.roiPlane2, state.roiPlane3].filter(Boolean).length;
    const badge = $('roi-teach-progress');
    if (badge) {
      badge.textContent = `三平面已框选 ${count}/3`;
      badge.className = count === 3 ? 'badge badge-ok' : 'badge badge-muted';
    }
    [
      ['btn-roi-plane1', 'roiPlane1'],
      ['btn-roi-plane2', 'roiPlane2'],
      ['btn-roi-plane3', 'roiPlane3'],
    ].forEach(([buttonId, stateKey]) => {
      $(buttonId)?.classList.toggle('done', Boolean(state[stateKey]));
      $(buttonId)?.classList.toggle('invalid', state.invalidRoiKeys.includes(stateKey));
    });
  }

  function clearLocalTemplateRois() {
    state.roiPlane1 = null;
    state.roiPlane2 = null;
    state.roiPlane3 = null;
    state.invalidRoiKeys = [];
    state.localTemplateGeometryValid = null;
    updateLocalTemplateRoiCount();
    updateMeasurementConfigProgress();
  }

  function normalizeLayerSpacingLine(line) {
    if (!line) return null;
    const normalized = {
      x1: Number(line.x1), y1: Number(line.y1),
      x2: Number(line.x2), y2: Number(line.y2),
      sample_radius: Math.max(4, Math.min(30, Number(line.sample_radius || 10))),
      depth_window_mm: Math.max(5, Math.min(80, Number(line.depth_window_mm || 25))),
    };
    if (![normalized.x1, normalized.y1, normalized.x2, normalized.y2].every(Number.isFinite)) {
      return null;
    }
    return normalized;
  }

  function updateLayerSpacingLineUI() {
    const button = $('btn-layer-spacing-line');
    if (!button) return;
    button.classList.toggle('done', Boolean(state.layerSpacingLine));
    button.classList.toggle('active', state.drawMode === 'line');
  }

  function applyLayerSpacingLine(line) {
    state.layerSpacingLine = normalizeLayerSpacingLine(line);
    state.displayLayerSpacingLine = null;
    updateLayerSpacingLineUI();
    updateMeasurementConfigProgress();
    draw();
  }

  function clearLayerSpacingLine() {
    state.layerSpacingLine = null;
    state.pendingLayerSpacingLine = null;
    state.displayLayerSpacingLine = null;
    state.lineDrawing = false;
    state.lineStart = null;
    if (state.drawMode === 'line') state.drawMode = 'rect';
    updateLayerSpacingLineUI();
    updateMeasurementConfigProgress();
  }

  /** 是否三个平面 ROI 已全部框选 */
  function hasAllLocalTemplateRois() {
    return Boolean(state.roiPlane1 && state.roiPlane2 && state.roiPlane3);
  }

  /** 构造传给后端的 local_template_rois 对象（去掉前端内部字段） */
  function cleanLocalTemplateRois() {
    const clean = (roi) => roi ? { x: roi.x, y: roi.y, w: roi.w, h: roi.h } : null;
    return {
      plane1: clean(state.roiPlane1),
      plane2: clean(state.roiPlane2),
      plane3: clean(state.roiPlane3),
    };
  }

  async function refreshCurrentRecipe(recipeId = null) {
    if (!CFG.currentRecipeUrl && !CFG.recipeApiUrl) return null;
    const requestSeq = ++state.recipeRequestSeq;
    try {
      let url;
      if (recipeId && CFG.recipeApiUrl) {
        const query = new URLSearchParams({ id: String(recipeId) });
        url = `${CFG.recipeApiUrl}?${query.toString()}`;
      } else {
        const query = new URLSearchParams({
          locate_type: currentLocateType(),
          layer_index: String(currentLayerIndex()),
        });
        url = `${CFG.currentRecipeUrl}?${query.toString()}`;
      }
      const res = await fetch(url);
      const data = apiPayload(await res.json());
      const recipe = data.recipe || data.recipes?.[0] || null;
      // 用户快速切换配方时，旧请求不得覆盖最后一次选择。
      if (requestSeq !== state.recipeRequestSeq) return null;
      state.currentRecipe = recipe;
      syncRansacThreshold(recipe?.roi_config || {});
      if (recipe && recipe.id && $('recipe-id')) {
        $('recipe-id').value = recipe.id;
      }
      state.standardRackModel = recipe?.reference_feature_config?.standard_rack_model || null;
      state.standardRackCandidate = null;
      if (typeof renderStandardRackModel === 'function') {
        renderStandardRackModel(state.standardRackModel);
      }
      const resultForRecipe = String(state.lastResultRecipeId || '') === String(recipe?.id || '')
        ? (state.lastResult || {})
        : {};
      renderLocalTemplate(resultForRecipe);
      renderLayerSpacing(resultForRecipe);
      return recipe;
    } catch (e) {
      if (requestSeq !== state.recipeRequestSeq) return null;
      state.currentRecipe = null;
      console.error('[加载当前3D配方]', e);
      renderLocalTemplate({});
      return null;
    }
  }

  function cleanTargetRoi() {
    if (!state.roi) return null;
    return {
      x: state.roi.x,
      y: state.roi.y,
      w: state.roi.w,
      h: state.roi.h,
      feature_type: state.roi.feature_type || 'rack_reference',
      ...(state.roi.polygon ? { polygon: state.roi.polygon } : {}),
    };
  }

  function selectedRansacThreshold() {
    const value = Number($('ransac-distance-threshold')?.value ?? 2);
    return Number.isFinite(value) && value >= 0.5 && value <= 20 ? value : 2.0;
  }

  function syncRansacThreshold(config) {
    const input = $('ransac-distance-threshold');
    if (!input) return;
    const value = Number(config?.ransac_distance_threshold_mm ?? 2.0);
    input.value = (Number.isFinite(value) && value >= 0.5 && value <= 20 ? value : 2.0).toFixed(1);
  }

  function measurementConfigPatch(changedKey = 'all') {
    if (changedKey === 'roi') {
      const targetRoi = cleanTargetRoi();
      return targetRoi ? { target_roi: targetRoi } : {};
    }
    const planeKeyByState = {
      roiPlane1: 'plane1',
      roiPlane2: 'plane2',
      roiPlane3: 'plane3',
    };
    if (planeKeyByState[changedKey]) {
      const roi = state[changedKey];
      return roi ? {
        local_template_rois: {
          [planeKeyByState[changedKey]]: { x: roi.x, y: roi.y, w: roi.w, h: roi.h },
        },
      } : {};
    }
    if (changedKey === 'layerSpacingLine') {
      const line = cleanLayerSpacingLine();
      return line ? { layer_spacing_line: line } : {};
    }
    if (changedKey === 'ransacThreshold') {
      return { ransac_distance_threshold_mm: selectedRansacThreshold() };
    }

    const config = {};
    const targetRoi = cleanTargetRoi();
    if (targetRoi) config.target_roi = targetRoi;
    const localRois = cleanLocalTemplateRois();
    const configuredLocalRois = Object.fromEntries(
      Object.entries(localRois).filter(([, roi]) => Boolean(roi)),
    );
    if (Object.keys(configuredLocalRois).length) {
      config.local_template_rois = configuredLocalRois;
    }
    const line = cleanLayerSpacingLine();
    if (line) config.layer_spacing_line = line;
    config.ransac_distance_threshold_mm = selectedRansacThreshold();
    return config;
  }

  function measurementConfigSummary(config = measurementConfigPatch('all')) {
    const localRois = config.local_template_rois || {};
    const items = [
      [Boolean(config.target_roi), '外框'],
      [Boolean(localRois.plane1), 'Π1'],
      [Boolean(localRois.plane2), 'Π2'],
      [Boolean(localRois.plane3), 'Π3'],
      [Boolean(config.layer_spacing_line), '层距线'],
    ];
    return {
      count: items.filter(([configured]) => configured).length,
      labels: items.filter(([configured]) => configured).map(([, label]) => label),
    };
  }

  function updateMeasurementConfigProgress() {
    const summary = measurementConfigSummary();
    const badge = $('roi-config-progress');
    if (badge) {
      badge.textContent = `五项位置 ${summary.count}/5`;
      badge.className = summary.count === 5 ? 'badge badge-ok' : 'badge badge-muted';
    }
    return summary;
  }

  function cleanLayerSpacingLine() {
    const line = state.layerSpacingLine;
    return line ? {
      x1: line.x1, y1: line.y1, x2: line.x2, y2: line.y2,
      sample_radius: line.sample_radius || 10,
      depth_window_mm: line.depth_window_mm || 25,
    } : null;
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

  function updateSelectedRecipeStandard(standard) {
    const sx = Number(standard?.x);
    const sy = Number(standard?.y);
    const sz = Number(standard?.z);
    if (![sx, sy, sz].every(Number.isFinite)) return;

    const select = document.getElementById('recipe-select');
    if (select && select.selectedIndex >= 0) {
      const option = select.options[select.selectedIndex];
      if (option) {
        option.dataset.sx = String(sx);
        option.dataset.sy = String(sy);
        option.dataset.sz = String(sz);
      }
    }

    const card = document.querySelector('.rl-recipe-card.selected');
    if (card) {
      card.dataset.sx = String(sx);
      card.dataset.sy = String(sy);
      card.dataset.sz = String(sz);
    }

    [
      ['recipe-card-sx', sx],
      ['recipe-card-sy', sy],
      ['recipe-card-sz', sz],
      ['d-sx', sx],
      ['d-sy', sy],
      ['d-sz', sz],
    ].forEach(([id, value]) => {
      const node = $(id);
      if (node) node.textContent = Number(value).toFixed(2);
    });
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

  function applyLocalTemplateRois(localTemplateRois) {
    const source = localTemplateRois || {};
    state.roiPlane1 = normalizePixelRoi(source.plane1);
    state.roiPlane2 = normalizePixelRoi(source.plane2);
    state.roiPlane3 = normalizePixelRoi(source.plane3);
    updateLocalTemplateRoiCount();
    updateMeasurementConfigProgress();
    draw();
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
    updateMeasurementConfigProgress();
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
      if (state.pendingLocalTemplateRois !== null) {
        applyLocalTemplateRois(state.pendingLocalTemplateRois);
        state.pendingLocalTemplateRois = null;
      }
      if (state.pendingLayerSpacingLine !== null) {
        applyLayerSpacingLine(state.pendingLayerSpacingLine);
        state.pendingLayerSpacingLine = null;
      }
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
      refreshActionState();
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
    const stageRect = $('rl-stage').getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(rect.width));
    canvas.height = Math.max(1, Math.round(rect.height));
    // 舞台有最小高度时图像会垂直居中；画布必须只覆盖实际图像，
    // 否则鼠标像素与点云像素在 Y 方向会产生系统性偏移。
    canvas.style.inset = 'auto';
    canvas.style.left = `${rect.left - stageRect.left}px`;
    canvas.style.top = `${rect.top - stageRect.top}px`;
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
    draw();
  }

  const roiOverlayStyles = [
    { key: 'roi',       label: '外框 ROI',     color: '#22c55e', fill: 'rgba(34,197,94,0.10)' },
    { key: 'roiPlane1', label: 'Π1 顶部横梁', color: '#0ea5e9', fill: 'rgba(14,165,233,0.16)' },
    { key: 'roiPlane2', label: 'Π2 左侧立柱', color: '#f59e0b', fill: 'rgba(245,158,11,0.16)' },
    { key: 'roiPlane3', label: 'Π3 底部横梁', color: '#ec4899', fill: 'rgba(236,72,153,0.16)' },
  ];

  function activeRoiOverlayStyle() {
    return roiOverlayStyles.find(({ key }) => key === (state.activeRoiStateKey || 'roi'))
      || roiOverlayStyles[0];
  }

  function realToDisplay(roi) {
    if (!roi) return null;
    const nat = naturalDims();
    if (!nat.w || !nat.h || !canvas.width || !canvas.height) return null;
    return {
      x: roi.x * canvas.width / nat.w,
      y: roi.y * canvas.height / nat.h,
      w: roi.w * canvas.width / nat.w,
      h: roi.h * canvas.height / nat.h,
    };
  }

  function realPointToDisplay(point) {
    const nat = naturalDims();
    if (!point || !nat.w || !nat.h || !canvas.width || !canvas.height) return null;
    return {
      x: point.x * canvas.width / nat.w,
      y: point.y * canvas.height / nat.h,
    };
  }

  function displayPointToReal(point) {
    const nat = naturalDims();
    return {
      x: Math.round(point.x * nat.w / canvas.width),
      y: Math.round(point.y * nat.h / canvas.height),
    };
  }

  function drawLayerSpacingLineOverlay(line, { preview = false } = {}) {
    if (!line) return;
    const start = line.displayCoordinates
      ? { x: line.x1, y: line.y1 }
      : realPointToDisplay({ x: line.x1, y: line.y1 });
    const end = line.displayCoordinates
      ? { x: line.x2, y: line.y2 }
      : realPointToDisplay({ x: line.x2, y: line.y2 });
    if (!start || !end) return;
    const nat = naturalDims();
    const radiusPx = line.displayCoordinates
      ? Number(line.sample_radius || 10)
      : Number(line.sample_radius || 10) * canvas.width / Math.max(1, nat.w);
    ctx.save();
    ctx.strokeStyle = '#16a34a';
    ctx.fillStyle = 'rgba(22,163,74,0.16)';
    ctx.lineWidth = preview ? 4 : 3;
    ctx.setLineDash(preview ? [7, 4] : []);
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
    ctx.setLineDash([]);
    [start, end].forEach((point) => {
      ctx.beginPath();
      ctx.arc(point.x, point.y, Math.max(5, radiusPx), 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(point.x, point.y, 3, 0, Math.PI * 2);
      ctx.fillStyle = '#16a34a';
      ctx.fill();
      ctx.fillStyle = 'rgba(22,163,74,0.16)';
    });
    const midX = (start.x + end.x) / 2;
    const midY = (start.y + end.y) / 2;
    const label = preview ? '层距测量线（绘制中）' : '层距测量线';
    ctx.font = '600 14px sans-serif';
    const labelWidth = ctx.measureText(label).width + 12;
    ctx.fillStyle = '#16a34a';
    ctx.fillRect(Math.max(0, midX - labelWidth / 2), Math.max(0, midY - 24), labelWidth, 20);
    ctx.fillStyle = '#fff';
    ctx.fillText(label, Math.max(6, midX - labelWidth / 2 + 6), Math.max(15, midY - 9));
    ctx.restore();
  }

  function drawRectOverlay(roi, style, { active = false, preview = false } = {}) {
    if (!roi || ![roi.x, roi.y, roi.w, roi.h].every(Number.isFinite)) return;
    ctx.save();
    ctx.strokeStyle = style.color;
    ctx.lineWidth = active ? 4 : 3;
    ctx.setLineDash(preview ? [6, 3] : (active ? [10, 4] : []));
    ctx.fillStyle = style.fill;
    ctx.fillRect(roi.x, roi.y, roi.w, roi.h);
    ctx.strokeRect(roi.x, roi.y, roi.w, roi.h);

    const label = preview ? `${style.label}（绘制中）` : style.label;
    ctx.setLineDash([]);
    ctx.font = '600 14px sans-serif';
    const labelWidth = ctx.measureText(label).width + 12;
    const labelX = Math.max(0, Math.min(roi.x, canvas.width - labelWidth));
    const labelY = roi.y >= 24 ? roi.y - 22 : roi.y + 4;
    ctx.fillStyle = style.color;
    ctx.fillRect(labelX, labelY, labelWidth, 20);
    ctx.fillStyle = '#fff';
    ctx.fillText(label, labelX + 6, labelY + 15);
    ctx.restore();
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 已完成的外框、Π1、Π2、Π3 始终同时显示；当前选中区域用虚线强调。
    roiOverlayStyles.forEach((style) => {
      const roi = state[style.key];
      if (!roi || (style.key === 'roi' && roi.displayPolygon?.length >= 2)) return;
      const invalid = state.invalidRoiKeys.includes(style.key);
      const displayStyle = invalid
        ? { ...style, label: `${style.label} · 提示`, color: '#d97706', fill: 'rgba(217,119,6,0.18)' }
        : style;
      drawRectOverlay(realToDisplay(roi), displayStyle, {
        active: style.key === (state.activeRoiStateKey || 'roi'),
      });
    });

    if (state.layerSpacingLine) drawLayerSpacingLineOverlay(state.layerSpacingLine);
    if (state.lineDrawing && state.displayLayerSpacingLine) {
      drawLayerSpacingLineOverlay(
        { ...state.displayLayerSpacingLine, displayCoordinates: true, sample_radius: 10 },
        { preview: true },
      );
    }

    // 外框 ROI 可以使用多边形，绘制它时也不隐藏三个平面矩形。
    if (state.roi && state.roi.displayPolygon && state.roi.displayPolygon.length >= 2) {
      const poly = state.roi.displayPolygon;
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
      poly.forEach((pt) => {
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#a855f7';
        ctx.fill();
      });
      ctx.fillStyle = '#a855f7';
      ctx.font = '600 14px sans-serif';
      ctx.fillText('✏ 外框 ROI', poly[0].x + 8, Math.max(18, poly[0].y - 6));
      ctx.restore();
    }

    // 正在描绘中的多边形实时预览。
    if (state.polyDrawing && state.polyPoints.length > 0) {
      const pts = state.polyPoints;
      ctx.save();
      ctx.strokeStyle = '#a855f7';
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 3]);
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
      if (state.polyMousePos) ctx.lineTo(state.polyMousePos.x, state.polyMousePos.y);
      ctx.stroke();
      ctx.setLineDash([]);
      pts.forEach((pt, idx) => {
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, idx === 0 ? 6 : 4, 0, Math.PI * 2);
        ctx.fillStyle = idx === 0 ? '#f59e0b' : '#a855f7';
        ctx.fill();
      });
      ctx.restore();
    }

    // 拖拽中的矩形只作为预览；鼠标释放后改由上面的持久 ROI 渲染。
    if (state.drawing && state.displayRoi) {
      drawRectOverlay(state.displayRoi, activeRoiOverlayStyle(), { active: true, preview: true });
    }
  }

  function pointerToCanvas(e) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(canvas.width, (e.clientX - rect.left) * canvas.width / rect.width)),
      y: Math.max(0, Math.min(canvas.height, (e.clientY - rect.top) * canvas.height / rect.height)),
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
    if (state.drawMode === 'line') {
      n.textContent = state.layerSpacingLine
        ? `层距测量线：(${state.layerSpacingLine.x1}, ${state.layerSpacingLine.y1}) → (${state.layerSpacingLine.x2}, ${state.layerSpacingLine.y2})`
        : '拖拽绘制层距测量线';
      return;
    }
    const key = state.activeRoiStateKey || 'roi';
    const style = roiOverlayStyles.find((item) => item.key === key) || roiOverlayStyles[0];
    const r = state[key];
    if (!r) {
      n.textContent = state.drawMode === 'polygon'
        ? '✏️ 单击添加顶点，双击闭合'
        : `拖拽绘制 ${style.label}`;
      return;
    }
    if (r.polygon && r.polygon.length > 0) {
      n.textContent = `${style.label}：多边形 ${r.polygon.length} 个顶点  包围盒 w=${r.w}  h=${r.h}`;
    } else {
      n.textContent = `${style.label}  x=${r.x}  y=${r.y}  w=${r.w}  h=${r.h}`;
    }
  }

  // ── 矩形拖拽绘制（原有模式） ────────────────────────────
  canvas.addEventListener('mousedown', (e) => {
    if (!state.token) return;
    if (state.drawMode === 'polygon') return;  // 多边形模式由 click 处理
    if (state.drawMode === 'line') {
      const point = pointerToCanvas(e);
      state.lineDrawing = true;
      state.lineStart = point;
      state.displayLayerSpacingLine = {
        x1: point.x, y1: point.y, x2: point.x, y2: point.y,
      };
      draw();
      return;
    }
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
    if (state.drawMode === 'line') {
      if (state.lineDrawing && state.lineStart) {
        const point = pointerToCanvas(e);
        state.displayLayerSpacingLine = {
          x1: state.lineStart.x, y1: state.lineStart.y,
          x2: point.x, y2: point.y,
        };
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
    if (state.drawMode === 'line') {
      if (!state.lineDrawing || !state.displayLayerSpacingLine) return;
      const displayLine = state.displayLayerSpacingLine;
      state.lineDrawing = false;
      state.lineStart = null;
      const length = Math.hypot(displayLine.x2 - displayLine.x1, displayLine.y2 - displayLine.y1);
      if (length < 12) {
        state.displayLayerSpacingLine = null;
        setStatus('层距测量线太短，请从上层对应点拖到下层对应点。');
        draw();
        return;
      }
      const start = displayPointToReal({ x: displayLine.x1, y: displayLine.y1 });
      const end = displayPointToReal({ x: displayLine.x2, y: displayLine.y2 });
      state.layerSpacingLine = {
        x1: start.x, y1: start.y, x2: end.x, y2: end.y,
        sample_radius: 10,
        depth_window_mm: 25,
      };
      state.displayLayerSpacingLine = null;
      state.drawMode = 'rect';
      updateLayerSpacingLineUI();
      draw();
      refreshActionState();
      autoSaveRoiToRecipe({ changedKey: 'layerSpacingLine' });
      return;
    }
    if (!state.drawing || !state.displayRoi) return;
    state.drawing = false;
    state.start = null;
    if (state.displayRoi.w < 3 || state.displayRoi.h < 3) { state.displayRoi = null; draw(); return; }
    const real = displayToReal(state.displayRoi);
    const roiData = { x: real.x, y: real.y, w: real.w, h: real.h, feature_type: 'rack_reference' };
    const key = state.activeRoiStateKey || 'roi';
    state[key] = roiData;
    state.invalidRoiKeys = state.invalidRoiKeys.filter((item) => item !== key);
    if (key !== 'roi') state.localTemplateGeometryValid = null;
    if (key === 'roi') {
      // 外框 ROI 自动保存到配方
      setReadout();
      syncRoiToRightSide();
      refreshActionState();
      autoSaveRoiToRecipe({ changedKey: 'roi' });
    } else {
      // 局部模板 ROI：更新三平面计数显示
      updateLocalTemplateRoiCount();
      setReadout();
      refreshActionState();
      draw();
      autoSaveRoiToRecipe({ changedKey: key });
    }
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
    autoSaveRoiToRecipe({ changedKey: 'roi' });
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
    if (measurementConfigSummary().count === 0) { setStatus('请先画好至少一项位置再保存。'); return; }
    const btn = $('btn-save-recipe');
    const origText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '保存中...';
    await autoSaveRoiToRecipe({ changedKey: 'all' });
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
      state.pointcloudConsumed = false;
      state.alignmentToken = null;
      state.lastResultId = null;
      state.lastResultOk = false;
      state.lastResultRecipeId = null;
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
    const key = state.activeRoiStateKey || 'roi';
    if (key === 'layerSpacingLine') {
      clearLayerSpacingLine();
      state.drawMode = 'line';
      state.activeRoiStateKey = 'layerSpacingLine';
      updateLayerSpacingLineUI();
      draw();
      setStatus('已清除层距测量线，请重新从上层对应点拖到下层对应点。');
      refreshActionState();
      return;
    }
    const style = roiOverlayStyles.find((item) => item.key === key) || roiOverlayStyles[0];
    state[key] = null;
    state.invalidRoiKeys = state.invalidRoiKeys.filter((item) => item !== key);
    if (key !== 'roi') state.localTemplateGeometryValid = null;
    state.displayRoi = null;
    state.alignmentToken = null;
    if (key === 'roi') {
      // 外框 ROI 还可能包含多边形状态。
      state.polyPoints = [];
      state.polyDrawing = false;
      state.polyMousePos = null;
      exitPolygonMode();
    }
    updateLocalTemplateRoiCount();
    draw(); setReadout();
    setStatus(`已清除「${style.label}」，请在点云图上重新拖拽框选。`);
    refreshActionState();
  });

  let ransacThresholdSaveTimer = null;
  async function saveRansacThresholdInput(input) {
    const value = Number(input.value);
    if (!Number.isFinite(value) || value < 0.5 || value > 20) {
      syncRansacThreshold(state.currentRecipe?.roi_config || {});
      setStatus('RANSAC距离阈值必须在 0.5～20.0 mm 之间。');
      return;
    }
    input.value = value.toFixed(1);
    const saved = await autoSaveRoiToRecipe({ changedKey: 'ransacThreshold' });
    if (saved) {
      setStatus(`✅ RANSAC距离阈值 ${value.toFixed(1)} mm 已保存到当前配方；下次计算生效。`);
    }
  }
  const ransacThresholdInput = $('ransac-distance-threshold');
  ransacThresholdInput?.addEventListener('input', () => {
    clearTimeout(ransacThresholdSaveTimer);
    ransacThresholdSaveTimer = setTimeout(() => saveRansacThresholdInput(ransacThresholdInput), 500);
  });
  ransacThresholdInput?.addEventListener('change', () => {
    clearTimeout(ransacThresholdSaveTimer);
    saveRansacThresholdInput(ransacThresholdInput);
  });

  // ── ROI 模式切换按鈕（外框/਀1/਀2/਀3）───────────────────────────────────
  (function bindRoiModeButtons() {
    const roiModes = [
      { id: 'btn-roi-target',  mode: 'target',  stateKey: 'roi' },
      { id: 'btn-roi-plane1',  mode: 'plane1',  stateKey: 'roiPlane1' },
      { id: 'btn-roi-plane2',  mode: 'plane2',  stateKey: 'roiPlane2' },
      { id: 'btn-roi-plane3',  mode: 'plane3',  stateKey: 'roiPlane3' },
    ];

    function setActiveRoiBtn(activeId) {
      $('btn-layer-spacing-line')?.classList.remove('active');
      roiModes.forEach(({ id }) => {
        const btn = $(id);
        if (btn) btn.classList.toggle('active', id === activeId);
      });
      state.activeRoiMode = activeId;
    }

    roiModes.forEach(({ id, mode, stateKey }) => {
      $(id)?.addEventListener('click', () => {
        if (!state.token) return;
        setActiveRoiBtn(id);
        // 清空当前画布待绘单元是 state.roi，切换后绘制的是对应的局部模板 ROI
        state.activeRoiStateKey = stateKey;
        state.drawMode = 'rect';
        draw();
        setReadout();
        setStatus(`请在点云图上框选「${id === 'btn-roi-target' ? '外框 ROI' : mode === 'plane1' ? 'Π1 顶部横梁' : mode === 'plane2' ? 'Π2 左侧立柱' : 'Π3 底部横梁'}」区域。`);
      });
    });

    // 初始化时默认激活「外框 ROI」按鈕
    setActiveRoiBtn('btn-roi-target');
    state.activeRoiMode = 'btn-roi-target';
    state.activeRoiStateKey = 'roi';
  }());

  $('btn-layer-spacing-line')?.addEventListener('click', () => {
    if (!state.token) { setStatus('请先采集或加载点云。'); return; }
    document.querySelectorAll('.rl-roi-editor-btn').forEach((button) => {
      button.classList.remove('active');
    });
    state.drawMode = 'line';
    state.activeRoiStateKey = 'layerSpacingLine';
    state.lineDrawing = false;
    state.lineStart = null;
    state.displayLayerSpacingLine = null;
    updateLayerSpacingLineUI();
    draw();
    setReadout();
    setStatus('请从上层基准点按住鼠标，拖到下层对应点；两个端点请落在同类钢架表面上。');
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

  $('btn-calibrate-standard')?.addEventListener('click', async () => {
    const recipeId = state.lastResultRecipeId;
    const rectangle = state.lastResult?.opening_rectangle || state.lastResult?.result_data?.opening_rectangle;
    if (!recipeId || !state.lastResultId || !rectangle) {
      setStatus('缺少配方、定位记录或三钢架拟合结果，不能建立标准模型。');
      return;
    }
    if (!state.lastResultOk) {
      setStatus('只有定位 OK 的三钢架拟合结果才能建立标准料架模型。');
      return;
    }
    const ok = window.confirm('确认用本次标准零位结果建立标准料架模型？将保存三根钢架中心线、正面平面、料架坐标系、点云模板和标准位姿。');
    if (!ok) return;

    const urlTemplate = CFG.calibrateStandardUrlTemplate || '';
    const url = urlTemplate.replace('__RECIPE_ID__', encodeURIComponent(recipeId));
    showLoading('建立标准料架模型...');
    try {
      const raw = await postJson(url, {
        result_id: state.lastResultId,
        note: `workbench-${new Date().toISOString()}`,
      });
      const data = apiPayload(raw);
      if (!data.success) {
        setStatus(data.error || '标准模板保存失败');
        return;
      }
      const standard = data.standard_template?.standard_pose || {};
      const recipe = data.standard_template?.reference_feature_config ? {
        ...(state.currentRecipe || {}),
        reference_feature_config: data.standard_template.reference_feature_config,
        standard_x: Number(standard.x || 0),
        standard_y: Number(standard.y || 0),
        standard_z: Number(standard.z || 0),
      } : null;
      if (recipe && String($('recipe-id')?.value || '') === String(recipeId)) {
        state.currentRecipe = recipe;
        updateSelectedRecipeStandard(standard);
      }
      state.standardRackModel = data.standard_template?.standard_rack_model || null;
      state.standardRackCandidate = null;
      if (typeof renderStandardRackModel === 'function') {
        renderStandardRackModel(state.standardRackModel);
      }
      setStatus('标准料架模型已保存；后续生产将以该坐标系和标准位姿计算整架补偿矩阵。');
    } catch (e) {
      setStatus('标准料架模型保存失败：' + e.message);
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
    // 未采集或当前点云已经计算过时，必须重新采集。禁止把建立标准
    // 模板时的同一帧再次用于验证，避免标准与自身比较得到假性零误差。
    if (!state.token || state.pointcloudConsumed) {
      showLoading('3D 相机采集中...');
      try {
        const captureApiUrl = CFG.captureUrl || CFG.legacyCaptureUrl || '/vision/api/rack-location/workbench/capture/';
        const captureRaw = await postJson(captureApiUrl, semanticPayload({
          recipe_id: $('recipe-id').value || null,
          rack_side: currentRackSide(),
        }));
        const captureData = apiPayload(captureRaw);
        if (!captureData.success) { setStatus(captureData.error || '采集失败，请检查相机连接'); hideLoading(); return; }
        state.token = captureData.pointcloud_token;
        state.source = captureData.source || '';
        state.captureRecipeId = $('recipe-id').value || null;
        state.captureLayerNo = currentLayerIndex();
        state.pointcloudConsumed = false;
        state.alignmentToken = null;
        state.roi = null; state.displayRoi = null;
        const previewUrl = captureData.pointcloud_preview_url || captureData.preview_image_url;
        if (previewUrl) { image.src = previewUrl + '?t=' + Date.now(); }
        image.dataset.naturalWidth = captureData.image_width;
        image.dataset.naturalHeight = captureData.image_height;
        image.style.display = 'block';
        canvas.style.display = 'block';
        $('rl-placeholder').style.display = 'none';
        setStatus('点云已采集，开始计算...');
      } catch (e) {
        setStatus('采集失败：' + e.message);
        hideLoading();
        return;
      }
    }

    showLoading('计算坐标偏差中...');
    try {
      // 优先使用工作台专用端点
      const calculateApiUrl = CFG.calculateUrl || CFG.legacyCalculateUrl || CFG.testLocateUrl || CFG.locateUrl || '/vision/api/rack-location/workbench/calculate/';
      console.log('[计算偏差] 使用API端点:', calculateApiUrl);

      // 五项位置统一走同一个清洗器，避免保存值与计算值发生漂移。
      const measurementConfig = measurementConfigPatch('all');
      const calculation = {
        pointcloud_token: state.token,
        roi: currentRoi3D(),
        roi_3d: currentRoi3D(),
        roi_config: measurementConfig,
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
      state.lastResultRecipeId = data.result?.recipe_id || calculation.recipe_id || null;
      if (String(state.currentRecipe?.id || '') !== String(state.lastResultRecipeId || '')) {
        await refreshCurrentRecipe(state.lastResultRecipeId);
      }
      renderResult(data.result);
      // 后端已经完整重跑算法并保存本次结果。保留 token 仅供结果导出，
      // 但标记为已消费；下一次“开始计算”会先采集新帧。
      state.pointcloudConsumed = true;
      state.alignmentToken = null;
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
      if (data.result.direct_detection_mode) {
        setStatus('计算完成：直接检测完成，本次3D记录已自动保存'
          + (data.result.warning_message ? ' · ' + data.result.warning_message : '。')
          + ' 再次计算将重新采集点云。');
      } else {
        setStatus(data.result.locate_ok
          ? '计算完成：定位 OK，本次3D记录已自动保存。'
          : ('计算完成：定位 NG，本次3D记录已自动保存 · ' + (data.result.error_message || data.result.error_code || '')));
      }

      // 保持当前配方不变，确保后续「保存为标准模板」仍绑定本次计算的配方。
    } catch (e) {
      setStatus('网络请求失败：' + e.message);
    } finally { hideLoading(); refreshActionState(); }
  });


  // ── 自动保存 ROI 到配方 ──────────────────────────────────
  async function autoSaveRoiToRecipe({ changedKey = 'all' } = {}) {
    const recipeId = $('recipe-id')?.value;
    if (!recipeId) { setStatus('未找到配方·请先选择配方'); return; }
    const roiConfig = measurementConfigPatch(changedKey);
    if (!Object.keys(roiConfig).length) { setStatus('当前项目没有可保存的位置数据'); return false; }
    const requestSeq = ++roiSaveRequestSeq;
    const payload = JSON.parse(JSON.stringify({ id: recipeId, roi_config: roiConfig }));
    const currentRecipeId = () => String($('recipe-id')?.value || '');
    const isCurrentRequest = () => (
      currentRecipeId() === String(recipeId) && requestSeq === roiSaveRequestSeq
    );
    if (currentRecipeId() === String(recipeId)) setStatus('正在保存位置数据到配方...');

    const executeSave = async () => {
      try {
        const raw = await postJson(
          CFG.recipeApiUrl || '/vision/api/vision/3d/recipes/',
          semanticPayload(payload),
          'PATCH',
        );
        const data = apiPayload(raw);
        if (!data.success) throw new Error(data.error || '保存失败，请查看控制台');
        const savedRecipe = data.recipe || null;
        if (currentRecipeId() === String(recipeId) && savedRecipe) {
          state.currentRecipe = savedRecipe;
        }
        if (isCurrentRequest()) {
          const summary = measurementConfigSummary(savedRecipe?.roi_config || measurementConfigPatch('all'));
          setStatus(`✅ 已保存到配方：${summary.labels.join('、')}（${summary.count}/5），可点击「开始计算」。`);
        }
        return true;
      } catch (e) {
        if (isCurrentRequest()) setStatus('位置数据保存失败：' + e.message);
        return false;
      }
    };

    const savePromise = roiSaveChain.then(executeSave, executeSave);
    roiSaveChain = savePromise.then(() => undefined, () => undefined);
    return savePromise;
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
    if (r?.result_id || r?.id) {
      state.lastResultId = r.result_id || r.id;
    }
    if (r?.recipe_id) {
      state.lastResultRecipeId = r.recipe_id;
    }
    const ok = r.locate_ok ?? r.is_success;
    state.lastResultOk = r?.direct_detection_mode
      ? Boolean(r?.plc_payload?.compensation_valid)
      : Boolean(ok);


    renderLocalTemplate(r);
    renderLayerSpacing(r);
    renderCompensation(r);

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
          ...measurementConfigPatch('all'),
        },
        result: state.lastResult,
        recipe_id: state.captureRecipeId || $('recipe-id')?.value || null,
        layer_no: state.captureLayerNo || currentLayerIndex(),
      };
    },
    load(payload) {
      if (!payload || !payload.pointcloud_token) throw new Error('数据包未返回有效点云');
      state.token = payload.pointcloud_token;
      state.pointcloudConsumed = false;
      state.source = payload.source || 'offline_package';
      state.captureRecipeId = payload.metadata?.recipe?.recipe_id || $('recipe-id')?.value || null;
      state.captureLayerNo = payload.metadata?.layer?.layer_no || currentLayerIndex();
      state.lastResult = payload.result || null;
      state.lastResultRecipeId = payload.result?.recipe_id || state.captureRecipeId || null;
      state.roi = null;
      state.displayRoi = null;
      clearLocalTemplateRois();
      clearLayerSpacingLine();
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
      state.pendingLocalTemplateRois = payload.roi_config?.local_template_rois || null;
      state.pendingLayerSpacingLine = normalizeLayerSpacingLine(payload.roi_config?.layer_spacing_line);
      syncRansacThreshold(payload.roi_config || state.currentRecipe?.roi_config || {});
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
      state.lastResultRecipeId = null;
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

  // ── 保存为标准模板 ────────────────────────────────────────
  const _btnSaveStd = $('btn-save-as-std');
  if (_btnSaveStd) {
    _btnSaveStd.addEventListener('click', async () => {
      // 必须绑定到生成当前模板的计算记录，不能使用可能已切换的下拉框值。
      const recipeId = state.lastResultRecipeId || state.captureRecipeId || $('recipe-id')?.value;
      const resultId = state.lastResultId;
      if (!recipeId) { setStatus('无选中配方'); return; }
      if (!window._tempCurTpl) { setStatus('无现场模板可保存，请先点击「开始计算」'); return; }
      if (!resultId) {
        setStatus('标准模板未保存：缺少本次计算记录，请重新点击「开始计算」。');
        return;
      }

      const btn = _btnSaveStd;
      const oldText = btn.textContent;
      btn.textContent = '保存中...';
      btn.disabled = true;

      try {
        const urlTemplate = CFG.calibrateStandardUrlTemplate || '';
        const url = urlTemplate.replace('__RECIPE_ID__', encodeURIComponent(recipeId));
        if (!url || url.includes('__RECIPE_ID__')) throw new Error('标准模板保存接口未配置');

        // 后端按 result_id 重新读取并校验三平面拟合结果，再持久化到对应配方。
        const raw = await postJson(url, {
          result_id: resultId,
          note: `local-template-workbench-${new Date().toISOString()}`,
        });
        const data = apiPayload(raw);
        if (!data.success) throw new Error(data.error || '未知错误');

        const savedTemplate = data.local_template_std || window._tempCurTpl;
        if (state.currentRecipe && String(state.currentRecipe.id) === String(recipeId)) {
          state.currentRecipe.local_template_std = savedTemplate;
        }
        setStatus(`✅ 标准模板已保存到配方 #${recipeId}，下次定位将以此作为基准。`);
        renderLocalTemplate({
          local_template_cur: window._tempCurTpl,
          local_template_validation: window._tempCurTplValidation,
        });
      } catch (e) {
        console.error('[保存标准模板]', e);
        setStatus('标准模板保存失败：' + e.message);
      } finally {
        btn.textContent = oldText;
        btn.disabled = false;
      }
    });
  }

}());

