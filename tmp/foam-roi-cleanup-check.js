

// ============================================================
//  泡棉检测工作台 · 前端逻辑
// ============================================================
const API = {
  refreshPreview:   '/vision/api/camera/preview/',
  captureAndInspect:'/vision/api/foam/capture-inspect/',
  uploadAndInspect: '/vision/api/foam/upload-inspect/',
  inspectionRecords: '/vision/api/foam/inspection-records/',
  calibration:      '/vision/api/foam/calibration/',
  saveCalibration:  '/vision/api/foam/calibration/save/',
  recipes:          '/vision/api/recipes/',
  recipeByPos:      '/vision/api/recipes/foam-2d/by-pos/',
  saveRecipe:       '/vision/api/recipes/foam-2d/save/',
  standardRoiStatus: (id) => `/vision/api/recipes/foam-2d/${id}/standard-roi/`,
  defaultRecipes:   '/vision/api/recipes/foam-2d/defaults/',
};
const FOAM_RECIPE_EDITING = true;
const WORKBENCH_QUERY = new URLSearchParams(window.location.search);
const WORKBENCH_LAYOUT_ID = WORKBENCH_QUERY.get('layout_id') || '';
const WORKBENCH_RECIPE_ID = WORKBENCH_QUERY.get('recipe_id') || '';
let recipeValidationCompleted = false;

// ── CSRF ─────────────────────────────────────────────────
function getCsrf() {
  return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
}

// ── Loading 遮罩 ─────────────────────────────────────────
function showLoading(msg = '处理中...') {
  if (document.getElementById('loading-overlay')) return;
  const el = document.createElement('div');
  el.id = 'loading-overlay';
  el.innerHTML = `<div class="loading-card"><div class="spinner"></div><p>${msg}</p></div>`;
  document.body.appendChild(el);
}
function hideLoading() {
  document.getElementById('loading-overlay')?.remove();
}

function showDetectionFeedback(message, isError = false) {
  const feedback = document.getElementById('detection-feedback');
  feedback.hidden = !message;
  feedback.textContent = message;
  feedback.style.background = isError ? '#fff7ed' : '#eff6ff';
  feedback.style.color = isError ? '#9a3412' : '#1e40af';
}

async function fetchDetectionJson(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  try {
    const response = await fetch(url, {...options, signal: controller.signal});
    let data;
    try {
      data = await response.json();
    } catch (error) {
      if (error.name === 'AbortError') throw error;
      const invalidResponse = new Error(`服务器返回内容无法解析（HTTP ${response.status}）`);
      invalidResponse.kind = 'response';
      throw invalidResponse;
    }
    return {response, data};
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('请求超过60秒。请检查相机连接及服务状态；后台任务可能仍在执行，请确认后再重试。');
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

// ── 预览图更新 ───────────────────────────────────────────
let cameraPreviewRequestInFlight = false;
let livePreviewEnabled = false;
let livePreviewTimer = null;
let lastCameraCaptureToken = '';
let currentStandardRoiReady = false;
let lastDetectionResult = null;
document.getElementById('btn-save-detection-images').addEventListener('click', async function () {
  const resultId = lastDetectionResult?.result_id;
  if (!resultId) return;
  this.disabled = true;
  try {
    const response = await fetch(`/vision/api/foam/records/${resultId}/save-images/`, {
      method: 'POST', headers: {'X-CSRFToken': getCsrf()}
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || '保存失败');
    showDetectionFeedback('本次原始图片已保存到：' + data.directory, false);
  } catch (error) { showDetectionFeedback(error.message, true); }
  finally { this.disabled = false; }
});

function stopLivePreview() {
  livePreviewEnabled = false;
  if (livePreviewTimer) window.clearTimeout(livePreviewTimer);
  livePreviewTimer = null;
  updateLivePreviewButton();
}

async function waitForCameraPreviewIdle(timeoutMs = 15000) {
  const startedAt = Date.now();
  while (cameraPreviewRequestInFlight && Date.now() - startedAt < timeoutMs) {
    await new Promise(resolve => window.setTimeout(resolve, 50));
  }
  return !cameraPreviewRequestInFlight;
}

function isCameraBusyError(msg) {
  const patterns = [
    '0x80000203', '0x80000206',           // MV_E_RESOURCE_BUSY / ACCESS_DENIED
    '-2147483133', '-2147483130',          // 同上十进制有符号
    '-2147483115',                         // 旧版 SDK 占用
    '相机被占用', '设备被占用', '打开设备失败',
    'resource busy', 'access denied',
    'open camera failed', 'mv_e_resource_busy',
  ];
  const lower = msg.toLowerCase();
  return patterns.some(p => lower.includes(p.toLowerCase()));
}

// 在页面顶部显示一个临时 toast 消息（不打断用户操作）
function showCameraToast(msg, type = 'warn') {
  const existing = document.getElementById('camera-toast');
  if (existing) existing.remove();
  const toast = document.createElement('div');
  toast.id = 'camera-toast';
  toast.style.cssText = [
    'position:fixed', 'top:16px', 'right:16px', 'z-index:9999',
    'max-width:380px', 'padding:12px 16px', 'border-radius:8px',
    'font-size:calc(13px + var(--ui-font-increase, 0px))', 'line-height:1.5', 'box-shadow:0 4px 20px rgba(0,0,0,.4)',
    type === 'warn'
      ? 'background:#92400e;color:#fef3c7;border:1px solid #b45309;'
      : 'background:#1e3a5f;color:#dbeafe;border:1px solid #3b82f6;',
    'transition:opacity .3s',
  ].join(';');
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 350); }, 4000);
}

async function refreshCameraPreview({ background = false } = {}) {
  if (cameraPreviewRequestInFlight) return false;
  cameraPreviewRequestInFlight = true;
  if (!background) showLoading('获取相机画面...');
  try {
    const {response: res, data} = await fetchDetectionJson(API.refreshPreview, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf(), 'Content-Type': 'application/json' },
    });
    if (res.ok && data?.success) {
      clearPendingFile();
      lastCameraCaptureToken = data.capture_token || '';
      setPreviewImage(data.image_url);
      return true;
    } else {
      let errorMsg = data.error || '未知错误';
      if (!background) showDetectionFeedback('获取相机画面失败：' + errorMsg, true);

      // 相机占用类错误：给出结构化提示
      if (isCameraBusyError(errorMsg)) {
        const friendlyMsg =
          '⚠️ 相机被占用，无法访问\n\n' +
          '可能原因：\n' +
          '• MVS 客户端软件正在使用相机\n' +
          '• 其他程序正在访问相机\n' +
          '• 上次使用未正常释放\n\n' +
          '解决方法：\n' +
          '1. 关闭 MVS 软件后再试\n' +
          '2. 刷新页面重试\n' +
          '3. 重启开发服务器';
        if (background) {
          // 实时预览：显示 toast，不弹 alert，不停止预览，让用户继续操作
          showCameraToast('📷 相机暂时被占用，将在下次自动重试...');
          return false;  // 返回 false 但由调用方决定是否停止
        } else {
          alert('获取预览失败\n\n' + friendlyMsg);
          return false;
        }
      } else if (errorMsg.includes('-2147483646') || errorMsg.includes('获取图像失败')) {
        errorMsg =
          '相机无法获取图像\n\n可能原因：\n' +
          '• 相机触发模式未配置\n' +
          '• 相机参数设置不正确\n\n' +
          '解决方法：\n' +
          '1. 使用 MVS 软件配置相机\n' +
          '2. 设置触发模式为"连续采集"\n' +
          '3. 查看《相机配置说明.md》';
        alert('获取预览失败\n\n' + errorMsg);
        return false;
      }

      if (background) {
        showCameraToast('📷 预览失败：' + errorMsg.slice(0, 80));
        return false;
      }
      alert('获取预览失败\n\n' + errorMsg);
      return false;
    }
  } catch (e) {
    if (background) {
      showCameraToast('📷 网络请求失败，将自动重试...');
      return false;
    }
    showDetectionFeedback('获取相机画面失败：' + e.message, true);
    alert('网络请求失败：' + e.message);
    return false;
  } finally {
    cameraPreviewRequestInFlight = false;
    if (!background) hideLoading();
  }
}

document.getElementById('btn-refresh-preview').addEventListener('click', () => {
  refreshCameraPreview();
});

function updateLivePreviewButton() {
  const button = document.getElementById('btn-live-preview');
  button.setAttribute('aria-pressed', livePreviewEnabled ? 'true' : 'false');
  button.textContent = livePreviewEnabled ? '⏹ 停止实时预览' : '▶ 开始实时预览';
  button.classList.toggle('btn-warning', livePreviewEnabled);
  button.classList.toggle('btn-secondary', !livePreviewEnabled);
}

async function runLivePreviewFrame() {
  if (!livePreviewEnabled) return;
  if (document.hidden) {
    livePreviewTimer = window.setTimeout(runLivePreviewFrame, 1000);
    return;
  }
  const success = await refreshCameraPreview({ background: true });
  if (!success) {
    // 相机占用是短暂错误，不停止实时预览，等待下一帧重试
    if (livePreviewEnabled) {
      livePreviewTimer = window.setTimeout(runLivePreviewFrame, 2000);  // 2s 后重试
    }
    return;
  }
  // 串行采集，上一帧完成后再请求下一帧，避免两个进程同时占用相机。
  if (livePreviewEnabled) {
    livePreviewTimer = window.setTimeout(runLivePreviewFrame, 250);
  }
}

document.getElementById('btn-live-preview').addEventListener('click', () => {
  if (livePreviewEnabled) {
    stopLivePreview();
  } else {
    livePreviewEnabled = true;
    updateLivePreviewButton();
    runLivePreviewFrame();
  }
});

window.addEventListener('beforeunload', () => {
  stopLivePreview();
});

function setPreviewImage(url) {
  const img = document.getElementById('preview-image');
  img.src = url + '?t=' + Date.now();
  img.style.display = 'block';
  document.getElementById('camera-placeholder').style.display = 'none';
  refreshPreviewRecipeRoi();
  updateCaptureButtonText();  // 更新按钮文本
}

// 暂存左侧导入的图片（等待「拍照检测」使用）
let pendingFile = null;
let pendingFileDataUrl = null;  // 保存图片的DataURL用于重复检测

// ── 视觉配方状态 ───────────────────────────────────────
let foam2DRecipes = [];
let manualSelectedRecipe = null;
let selectedRecipeForEdit = null;

function currentPOS() {
  return Number(document.getElementById('pos-index').value || 0);
}
function activeFoam2DRecipe() {
  const active = foam2DRecipes.filter(item => item.is_active);
  return active.length === 1 ? active[0] : null;
}
function currentDetectionRecipe() {
  if (manualSelectedRecipe) return manualSelectedRecipe;
  if (FOAM_RECIPE_EDITING) return selectedRecipeForEdit;
  return activeFoam2DRecipe();
}
function currentDetectionPos() {
  return currentPOS();
}

// ── 配方自动递增：检测完成后自动切换到下一个配方 ──────────────────────
function autoIncrementRecipe() {
  // 如果有手动选择的临时配方，不自动递增

  const currentPos = currentPOS();
  console.log('当前 POS:', currentPos);

  // Recipe choice is fixed for the rack; POS is only a result sequence.
  const nextPos = currentPos + 1;

  // 更新POS输入框
  const posInput = document.getElementById('pos-index');
  if (posInput) {
    posInput.value = nextPos;
    // 触发change事件以更新UI
    posInput.dispatchEvent(new Event('change'));

    // 显示提示信息
    showRecipeChangeNotification(currentPos, nextPos);
  }
}

// ── 显示配方切换提示 ─────────────────────────────────────────
function showRecipeChangeNotification(fromPos, toPos) {
  const status = document.getElementById('calibration-status');
  if (!status) return;

  const originalText = status.textContent;
  const originalColor = status.style.color;

  status.textContent = `✅ 检测完成，已自动切换：POS ${fromPos} → POS ${toPos}`;
  status.style.color = '#059669';
  status.style.fontWeight = '700';

  // 3秒后恢复原样
  setTimeout(() => {
    status.textContent = originalText;
    status.style.color = originalColor;
    status.style.fontWeight = '';
  }, 3000);
}
function roiToRatio(roi, recipe) {
  if (roi && roi.type === 'polygon') {
    return roi;
  }
  // 兼容两种格式：
  // 1. 比例格式（新格式）：{x1r, y1r, x2r, y2r} 或数组 [x1r,y1r,x2r,y2r]，值在 0~1 之间
  // 2. 像素格式（旧格式）：{x, y, width, height}，需要除以图像尺寸

  // 检测是否为比例格式（新格式）
  if ('x1r' in roi) {
    // 新格式：直接返回比例坐标
    return [Number(roi.x1r), Number(roi.y1r), Number(roi.x2r), Number(roi.y2r)];
  }

  // 旧格式（像素格式）：必须使用保存时记录的图像尺寸来还原比例
  // ⚠️ 关键：必须用配方保存时的 image_width/image_height，而非当前显示图片的 naturalWidth
  // 否则：如果当前预览图与保存时分辨率不同，比例坐标会错误
  const w = Number(recipe.image_width || 1280);
  const h = Number(recipe.image_height || 720);

  console.log(`[ROI转换] 配方图像尺寸=${w}x${h}, ROI像素=(${roi.x},${roi.y}), 尺寸=${roi.width}x${roi.height}`);

  return [
    Number(roi.x || 0) / w,
    Number(roi.y || 0) / h,
    (Number(roi.x || 0) + Number(roi.width || 0)) / w,
    (Number(roi.y || 0) + Number(roi.height || 0)) / h,
  ];
}
function applyRecipeRoiToOverlay(recipe) {
  if (!recipe?.roi_config) return;
  const left = recipe.roi_config.leftFoamROI;
  const right = recipe.roi_config.rightFoamROI;
  if (left) cal.rois.left = roiToRatio(left, recipe);
  if (right) cal.rois.right = roiToRatio(right, recipe);
  cal.rois.layer = recipe.roi_config.layerSearchROI ? roiToRatio(recipe.roi_config.layerSearchROI, recipe) : null;
  ['body1','body2'].forEach((key,index) => {
    const anchor = recipe.roi_config.productAnchorROIs?.[index];
    cal.rois[key] = anchor ? roiToRatio(anchor,recipe) : null;
  });
  renderRoiBoxes();
  console.log('已应用配方 ROI:', recipe.name, 'POS:', recipe.pos);
}
function refreshPreviewRecipeRoi() {
  const redraw = () => {
    const recipe = currentDetectionRecipe();
    if (recipe?.roi_config && !cal.dirty) {
      // 用户尚未手动画过 ROI，用配方数据初始化显示
      applyRecipeRoiToOverlay(recipe);
    } else {
      // 用户已手动标注或无配方，只重绘已有 cal.rois
      renderRoiBoxes();
    }
  };
  if (window.requestAnimationFrame) {
    window.requestAnimationFrame(redraw);
  } else {
    setTimeout(redraw, 0);
  }
}

async function requestDetection(url, options) {
  const requestStarted = performance.now();
  let response;
  let data;
  try {
    ({response, data} = await fetchDetectionJson(url, options));
  } catch (error) {
    return {
      ok: false,
      kind: error.kind || 'network',
      message: error?.message || '无法连接检测服务器',
    };
  }

  if (!response.ok || !data?.success) {
    return {
      ok: false,
      kind: 'detection',
      message: data?.error || `检测服务返回 HTTP ${response.status}`,
    };
  }

  if (!data.result || typeof data.result !== 'object') {
    return {
      ok: false,
      kind: 'response',
      message: '检测服务未返回有效的结果数据',
    };
  }

  if (data.result.timings_ms) {
    console.info('泡棉检测分段耗时(ms):', data.result.timings_ms);
  }
  data.result.browser_request_started = requestStarted;
  data.result.browser_response_received = performance.now();
  return { ok: true, result: data.result };
}

function showDetectionRequestError(outcome) {
  const titles = {
    network: '网络请求失败',
    response: '服务器响应异常',
    detection: '检测失败',
  };
  const title = titles[outcome.kind] || '检测失败';
  showDetectionFeedback(`${title}：${outcome.message}`, true);
}

function renderDetectionResultSafely(result) {
  try {
    renderResult(result);
    showDetectionFeedback('');
    return true;
  } catch (error) {
    console.error('检测成功，但结果界面渲染失败:', error, result);
    showDetectionFeedback(`检测已完成，但结果显示失败：${error?.message || '未知界面错误'}\n请刷新页面后重试。`, true);
    return false;
  }
}

// ── 拍照检测：自动判断使用相机还是导入图片 ───────────────────────────
document.getElementById('btn-capture-inspect').addEventListener('click', async () => {
  const captureButton = document.getElementById('btn-capture-inspect');
  if (captureButton.disabled) return;
  const clickStarted = performance.now();
  document.getElementById('detection-timing').textContent = '正在计时…';
  captureButton.disabled = true;
  captureButton.textContent = '⏳ 正在检测…';
  showDetectionFeedback('正在检查配方并准备检测…');
  try {
    const detectionPos = currentDetectionPos();

    stopLivePreview();
    if (!(await waitForCameraPreviewIdle())) {
      throw new Error('相机预览尚未结束，请稍后重试。');
    }

    if (!(await ensureStandardRoiForDetection())) {
      captureButton.disabled = false;
      return;
    }

    if (pendingFile) {
      // 有导入图片 → 走上传检测接口（可以重复使用同一张图片）
      showLoading('检测导入图片...');
      const fd = new FormData();
      fd.append('image', pendingFile);
      fd.append('position_index', detectionPos);
      const recipe = currentDetectionRecipe();
      if (recipe?.id) fd.append('recipe_id', recipe.id);
      fd.append('use_recipe', 'true');
      try {
        const outcome = await requestDetection(API.uploadAndInspect, {
          method: 'POST',
          headers: { 'X-CSRFToken': getCsrf() },
          body: fd,
        });
        if (outcome.ok) outcome.result.browser_click_started = clickStarted;
      if (outcome.ok && renderDetectionResultSafely(outcome.result)) {
          // 自动递增配方到下一个POS
          autoIncrementRecipe();

          // 保持图片在预览区，允许继续检测
          if (pendingFileDataUrl) {
            const img = document.getElementById('preview-image');
            img.src = pendingFileDataUrl;
          }
        } else {
          if (!outcome.ok) showDetectionRequestError(outcome);
        }
      } catch (e) {
        console.error('检测流程发生意外错误:', e);
        alert('检测流程异常：' + e.message);
      } finally {
        hideLoading();
        captureButton.disabled = false;
      }
      return;
    }

    // 无导入图片 → 走相机拍照接口
    const previewWasActive = livePreviewEnabled || cameraPreviewRequestInFlight;
    stopLivePreview();
    showLoading(previewWasActive ? '正在结束实时预览并拍照检测...' : '拍照检测中...');
    try {
      // 若预览帧正在采集，先等它释放相机，避免正式检测触发 SDK busy 后
      // 进入 1s/2s 退避重试。
      await waitForCameraPreviewIdle();
      const outcome = await requestDetection(API.captureAndInspect, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrf(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          position_index: detectionPos,
          recipe_id: currentDetectionRecipe()?.id,
          use_recipe: true,
        }),
      });
      if (outcome.ok) outcome.result.browser_click_started = clickStarted;
      if (outcome.ok && renderDetectionResultSafely(outcome.result)) {
        // 自动递增配方到下一个POS
        autoIncrementRecipe();
      } else {
        if (!outcome.ok) showDetectionRequestError(outcome);
      }
    } catch (e) {
      console.error('检测流程发生意外错误:', e);
      alert('检测流程异常：' + e.message);
    } finally {
      hideLoading();
      captureButton.disabled = false;
    }
  } catch (error) {
    console.error('检测准备失败:', error);
    showDetectionFeedback('检测失败：' + error.message, true);
  } finally {
    hideLoading();
    captureButton.disabled = false;
    updateCaptureButtonText();
  }
});

// ── 左侧「导入图片」：显示在左侧预览区，可标 ROI，再检测 ───────────
document.getElementById('btn-upload-left').addEventListener('click', () => {
  document.getElementById('file-upload-preview').click();
});
async function previewImportedFile(file) {
  stopLivePreview();
  if (!(await waitForCameraPreviewIdle())) {
    throw new Error('相机预览尚未结束，请稍后重新导入');
  }
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('无法读取所选图片'));
    reader.readAsDataURL(file);
  });
  const decoded = new Image();
  decoded.src = dataUrl;
  try { await decoded.decode(); }
  catch (_) { throw new Error('浏览器无法显示此图片，请使用 PNG、JPEG 或 BMP 格式'); }
  pendingFile = file;
  pendingFileDataUrl = dataUrl;
  lastCameraCaptureToken = '';
  const img = document.getElementById('preview-image');
  img.onload = () => refreshPreviewRecipeRoi();
  img.src = dataUrl;
  img.style.display = 'block';
  document.getElementById('camera-placeholder').style.display = 'none';
  setPendingBadge(file.name);
  updateCaptureButtonText();
  // A new input must not retain an annotated image from the previous inspection.
  const resultImage = document.getElementById('result-image');
  resultImage.onload = resultImage.onerror = null;
  resultImage.removeAttribute('src');
  resultImage.style.display = 'none';
  const placeholder = document.getElementById('result-placeholder');
  placeholder.textContent = '原图已导入，检测完成后显示标注结果图';
  placeholder.style.display = '';
}

document.getElementById('file-upload-preview').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try { await previewImportedFile(file); }
  catch (error) { showDetectionFeedback(error.message, true); }
  finally { e.target.value = ''; }
});

// ============================================================
// 标准 ROI 面板 —— ROI 即标准，显示当前配方 ROI 尺寸
// ============================================================

function showPublishFeedback(message, isError = true) {
  const feedback = document.getElementById('recipe-publish-feedback');
  if (!feedback) return;
  feedback.hidden = false;
  feedback.textContent = message;
  feedback.style.color = isError ? '#9a3412' : '#166534';
  feedback.style.background = isError ? '#fff7ed' : '#f0fdf4';
}

function updateStandardRoiPanel(status) {
  currentStandardRoiReady = Boolean(status?.ready);
  for (const side of ['left', 'right']) {
    const sideData = status?.sides?.[side] || {};
    const statusEl = document.getElementById(`sm-${side}-status`);
    const detailEl = document.getElementById(`sm-${side}-detail`);
    if (!statusEl) continue;

    if (sideData.exists) {
      statusEl.className = status?.ready ? 'sm-status sm-ok' : 'sm-status sm-missing';
      statusEl.textContent = '已配置';
      if (detailEl) {
        detailEl.textContent = `面积 ${sideData.pixels || sideData.pixel_count || 0} px² · 中心 (${Number(sideData.centroid_x || 0).toFixed(1)}, ${Number(sideData.centroid_y || 0).toFixed(1)}) px`;
        detailEl.style.display = 'block';
      }
    } else {
      statusEl.className = 'sm-status sm-missing';
      statusEl.textContent = '⚠️ 未保存有效 ROI';
      if (detailEl) {
        detailEl.textContent = sideData.error || '请绘制标准 ROI 并保存配方';
        detailEl.style.display = 'block';
      }
    }
  }
  const message = document.getElementById('standard-roi-message');
  if (message) {
    message.textContent = status?.ready
      ? '左右标准 ROI 已配置'
      : (status?.reason || '请配置左右标准 ROI');
    message.style.color = status?.ready ? '#166534' : '#b45309';
  }
}

async function loadStandardRoiStatus(recipeId) {
  if (!recipeId) {
    updateStandardRoiPanel({ready:false, reason:'请先保存配方', sides:{}});
    return;
  }
  try {
    const response = await fetch(API.standardRoiStatus(recipeId));
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || 'ROI 状态查询失败');
    updateStandardRoiPanel(data);
  } catch (error) {
    updateStandardRoiPanel({ready:false, reason:error.message, sides:{}});
  }
}

async function ensureStandardRoiForDetection() {
  const recipe = currentDetectionRecipe();
  if (cal.dirty) {
    showDetectionFeedback('ROI 已修改，请先保存到配方。', true);
    return false;
  }
  if (currentStandardRoiReady || recipe?.standard_roi_status?.ready || recipe?.standard_template_status?.ready) return true;
  showDetectionFeedback('请绘制有效的左右标准 ROI 并保存配方；无需建立图片模板。', true);
  return false;
}

// 检测前只检查已保存的标准 ROI，不取图或建立图片模板。
window.ensureStandardRoiForDetection = ensureStandardRoiForDetection;







function setPendingBadge(name) {
  let badge = document.getElementById('pending-file-badge');
  if (!badge) {
    badge = document.createElement('div');
    badge.id = 'pending-file-badge';
    badge.style.cssText = [
      'margin-top:8px', 'padding:6px 10px',
      'background:#fef9c3', 'border:1px solid #fbbf24',
      'border-radius:6px', 'font-size:calc(12px + var(--ui-font-increase, 0px))', 'color:#78350f',
      'display:flex', 'align-items:center', 'gap:8px',
    ].join(';');
    document.querySelector('.cam-controls').insertAdjacentElement('afterend', badge);
  }
  badge.replaceChildren();
  badge.append('⏳ ');
  const label = document.createElement('strong');
  label.textContent = `已导入：${name}`;
  badge.append(label, '，可标定 ROI 后点「拍照检测」（不调用相机）');
  const clearButton = document.createElement('button');
  clearButton.type = 'button';
  clearButton.textContent = '✕ 清除';
  clearButton.style.cssText = [
    'margin-left:auto', 'padding:2px 6px', 'font-size:calc(11px + var(--ui-font-increase, 0px))',
    'border:1px solid #d97706', 'border-radius:4px',
    'background:#fff', 'color:#b45309', 'cursor:pointer',
  ].join(';');
  clearButton.addEventListener('click', clearPendingFile);
  badge.appendChild(clearButton);
  badge.style.display = 'flex';
}

function clearPendingFile() {
  pendingFile = null;
  pendingFileDataUrl = null;
  const badge = document.getElementById('pending-file-badge');
  if (badge) badge.style.display = 'none';
  updateCaptureButtonText();
}

function updateCaptureButtonText() {
  const btn = document.getElementById('btn-capture-inspect');
  if (btn) {
    if (pendingFile) {
      btn.innerHTML = '🔍 检测图片';
    } else {
      btn.innerHTML = '📸 拍照检测';
    }
  }
}

// ── 右侧「导入图片检测」：先显示原图，再上传并检测 ───────────
document.getElementById('btn-upload').addEventListener('click', () => {
  document.getElementById('file-upload').click();
});
document.getElementById('file-upload').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try { await previewImportedFile(file); }
  catch (error) {
    showDetectionFeedback(error.message, true);
    e.target.value = '';
    return;
  }
  if (!(await ensureStandardRoiForDetection())) {
    e.target.value = '';
    return;
  }
  const detectionPos = currentDetectionPos();
  const fd = new FormData();
  fd.append('image', file);
  fd.append('position_index', detectionPos);
  const recipe = currentDetectionRecipe();
  if (recipe?.id) fd.append('recipe_id', recipe.id);
  fd.append('use_recipe', 'true');
  showLoading('上传并检测图片...');
  try {
    const outcome = await requestDetection(API.uploadAndInspect, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() },
      body: fd,
    });
    if (outcome.ok) {
      renderDetectionResultSafely(outcome.result);
    } else {
      showDetectionRequestError(outcome);
    }
  } catch (e) {
    console.error('检测流程发生意外错误:', e);
    alert('检测流程异常：' + e.message);
  } finally {
    hideLoading();
    e.target.value = '';
  }
});


// ── 渲染检测结果 ──────────────────────────────────────────
function showDetectionTiming(r, imageLoaded = false) {
  const started = r.browser_click_started ?? r.browser_request_started;
  if (started == null) return;
  const seconds = ms => (ms / 1000).toFixed(2) + '秒';
  const timing = r.timings_ms || {};
  const parts = [imageLoaded ? '点击至结果图显示 ' + seconds(performance.now() - started)
                            : '点击至判定返回 ' + seconds(r.browser_response_received - started)];
  parts.push('准备 ' + seconds(r.browser_request_started - started));
  parts.push('请求 ' + seconds(r.browser_response_received - r.browser_request_started));
  if (timing.camera_request != null) parts.push('其中取图 ' + seconds(timing.camera_request));
  if (timing.algorithm_and_archive != null) parts.push('计算及出图 ' + seconds(timing.algorithm_and_archive));
  document.getElementById('detection-timing').textContent = parts.join(' · ');
}

function renderResult(r) {
  showDetectionTiming(r);
  console.log('渲染检测结果:', r);
  lastDetectionResult = r;
  document.getElementById('btn-save-detection-images').disabled = false;
  if (FOAM_RECIPE_EDITING) {
    recipeValidationCompleted = Boolean(r.is_passed);
    const recipeState = document.getElementById('foam-recipe-save-state');
    if (recipeState) {
      recipeState.textContent = r.is_passed ? '试跑通过' : '试跑待复核';
      recipeState.classList.toggle('saved', Boolean(r.is_passed));
    }
  }


  // 判定横幅
  const banner = document.getElementById('verdict-banner');
  banner.className = 'verdict-banner ' + (r.is_passed ? 'pass' : 'fail');
  document.getElementById('verdict-icon').textContent = r.is_passed ? '✅' : '❌';
  document.getElementById('verdict-text').textContent = r.inspection_status === 'INVALID'
    ? '检测无效 · 请检查图像与配置' : (r.is_passed ? '检测合格 · OK' : '检测不合格 · NG');
  let sub = r.is_passed
    ? '泡棉已检测到，贴附状态合格，进入下一循环'
    : '泡棉检测异常，请查看下方详细信息';
  if (r.product_registration?.status === 'REGISTERED') {
    sub += ` · 已补偿产品位移 X ${r.product_registration.shift_x_px.toFixed(1)} / Y ${r.product_registration.shift_y_px.toFixed(1)} px，结果图为产品基准坐标`;
  } else if (r.product_registration?.status === 'INVALID') {
    sub += ' · 产品基准定位失败：' + r.product_registration.reason;
  }
  document.getElementById('verdict-sub').textContent = sub;
  const sideStates = Object.values(r.sides || r.result_data?.sides || {});
  const coverageOk = sideStates.every(foamCoverageValid);
  const separated = sideStates.some(d => d.decision_mode === 'separated-v2');
  const presentOk = Boolean(r.is_present) && (separated || coverageOk);
  const alignedOk = presentOk && Boolean(r.is_aligned);
  setMetricCard('card-present', 'value-present', presentOk,
    !r.is_present ? '未检出' : separated ? '已检测（完整性另判）' : coverageOk ? '已检测' : '覆盖不足', '●');
  setMetricCard('card-aligned', 'value-aligned', alignedOk,
    !presentOk ? '无法确认' : alignedOk ? '对齐' : '偏移', '↔');


  // 显示详细结果区域
  document.getElementById('detailed-result').style.display = 'block';

  // 配方标题
  const recipeTitle = `【POS${r.position_index} 配方 - 第${r.position_index + 1}层泡棉检测】`;
  document.getElementById('result-recipe-title').textContent = recipeTitle;

  // 渲染左右侧结果
  if (r.sides && (r.sides.left || r.sides.right)) {
    renderSideResult('left', r.sides.left, r);
    renderSideResult('right', r.sides.right, r);
  } else {
    // 兼容旧格式：没有sides字段时隐藏详细区域
    document.getElementById('detailed-result').style.display = 'none';
  }

  // 最终判定
  const finalDiv = document.getElementById('final-verdict');
  const finalText = document.getElementById('final-verdict-text');
  if (r.is_passed) {
    finalDiv.style.background = 'linear-gradient(135deg, #dcfce7 0%, #f0fdf4 100%)';
    finalDiv.style.border = '2px solid #10b981';
    finalText.style.color = '#059669';
    finalText.textContent = '✓ 合格';
  } else {
    finalDiv.style.background = 'linear-gradient(135deg, #fee2e2 0%, #fef2f2 100%)';
    finalDiv.style.border = '2px solid #ef4444';
    finalText.style.color = '#dc2626';

    // 分析不合格原因
    let reason = '';
    if (r.inspection_status === 'INVALID') {
      reason = '图像或测量不可靠，请检查配置及拍摄条件';
    } else if (r.sides) {
      const leftNG = r.sides.left && !r.sides.left.is_present;
      const rightNG = r.sides.right && !r.sides.right.is_present;
      if (leftNG && rightNG) {
        reason = '左右侧泡棉均不存在';
      } else if (leftNG) {
        reason = '左侧泡棉' + getDefectReason(r.sides.left);
      } else if (rightNG) {
        reason = '右侧泡棉' + getDefectReason(r.sides.right);
      } else {
        // 存在但不合格
        const leftReason = getSideIssue(r.sides.left);
        const rightReason = getSideIssue(r.sides.right);
        if (leftReason && rightReason) {
          reason = `左侧${leftReason}，右侧${rightReason}`;
        } else {
          reason = leftReason || rightReason || '质量不达标';
        }
      }
    } else {
      reason = formatDefect(r.defect_type);
    }
    finalText.textContent = '✗ 不合格 - ' + reason;
  }

  // Only hide the placeholder after the annotated image actually loads.
  const resultImg = document.getElementById('result-image');
  const resultPlaceholder = document.getElementById('result-placeholder');
  resultImg.style.display = 'none';
  resultPlaceholder.style.display = '';
  resultPlaceholder.textContent = r.result_image_url ? '正在加载标注结果图…' : '本次检测未生成标注结果图';
  resultImg.onload = () => {
    resultImg.style.display = 'block';
    resultPlaceholder.style.display = 'none';
    showDetectionTiming(r, true);
  };
  resultImg.onerror = () => {
    resultImg.style.display = 'none';
    resultPlaceholder.style.display = '';
    resultPlaceholder.textContent = '标注结果图加载失败，请检查图片服务；导入原图仍显示在左侧。';
  };
  if (r.result_image_url) {
    resultImg.src = r.result_image_url + (r.result_image_url.includes('?') ? '&' : '?') + 't=' + Date.now();
  } else {
    resultImg.removeAttribute('src');
  }

  // 详细数值（保留原有显示）
  document.getElementById('d-pos').textContent   = r.position_index;
  document.getElementById('d-recipe').textContent = r.recipe?.name || currentDetectionRecipe()?.name || '默认配置';

  const overallCoverage = Math.max(0, Math.min(1, Number(r.coverage_ratio) || 0));
  document.getElementById('d-cov').textContent   = (overallCoverage * 100).toFixed(1) + '%';
  document.getElementById('d-ox').textContent    = (r.offset_x_px > 0 ? '+' : '') + Number(r.offset_x_px).toFixed(1) + ' px' + (r.offset_x_mm ? ' (' + (r.offset_x_mm > 0 ? '+' : '') + Number(r.offset_x_mm).toFixed(2) + ' mm)' : '');
  document.getElementById('d-oy').textContent    = (r.offset_y_px > 0 ? '+' : '') + Number(r.offset_y_px).toFixed(1) + ' px' + (r.offset_y_mm ? ' (' + (r.offset_y_mm > 0 ? '+' : '') + Number(r.offset_y_mm).toFixed(2) + ' mm)' : '');
  document.getElementById('detail-row').style.display = 'flex';
  if (!r.is_passed && r.defect_type) {
    document.getElementById('d-defect').textContent = formatDefect(r.defect_type);
    document.getElementById('d-defect-chip').style.display = '';
  } else {
    document.getElementById('d-defect-chip').style.display = 'none';
  }

  // 同步更新左侧预览的ROI框
  syncResultRecipeToPreview(r);
}

// ── 渲染单侧结果（新增）────────────────────────────────────
function foamCoverageValid(data) {
  if (!data || !data.is_present || data.is_complete === false) return false;
  if (data.inspection_status === 'INVALID') return false;
  if (data.decision_mode === 'separated-v2') return data.is_complete === true;
  const threshold = data.coverage_threshold ?? 0;
  return Number(data.coverage_ratio ?? 0) >= Number(threshold);
}

function renderSideResult(side, data, fullResult) {
  if (!data) return;

  const prefix = side; // 'left' or 'right'
  const sideName = side === 'left' ? '左侧' : '右侧';

  // 状态徽章
  const badge = document.getElementById(`${prefix}-status-badge`);
  if (foamCoverageValid(data) && data.is_aligned) {
    badge.textContent = '✓ 合格';
    badge.style.background = '#dcfce7';
    badge.style.color = '#059669';
    badge.style.border = '1px solid #10b981';
  } else {
    const defect = getDefectReason(data);
    badge.textContent = '✗ 不合格 (缺陷: ' + defect + ')';
    badge.style.background = '#fee2e2';
    badge.style.color = '#dc2626';
    badge.style.border = '1px solid #ef4444';
  }

  // 获取阈值
  const coverageThreshold = fullResult.sides?.[side]?.coverage_threshold ?? 0.85;

  const maxOffsetMm = data.max_offset_mm;
  const maxOffsetPx = data.max_offset_px ?? 30;
  const maxOffsetXMm = data.max_offset_x_mm ?? maxOffsetMm;
  const maxOffsetYMm = data.max_offset_y_mm ?? maxOffsetMm;
  const maxOffsetXPx = data.max_offset_x_px ?? maxOffsetPx;
  const maxOffsetYPx = data.max_offset_y_px ?? maxOffsetPx;

  // 覆盖率
  // 后端覆盖率按 0~1 返回；这里再做一次边界保护，兼容旧检测记录。
  const coverage = Math.max(0, Math.min(1, Number(data.coverage_ratio) || 0));
  const detectedPixels = data.detected_pixels || 0;
  const standardPixels = data.standard_pixels || 0;
  const coveragePercent = (coverage * 100).toFixed(1) + '%';
  const pixelInfo = standardPixels ? (data.coverage_source === 'standard_overlap'
    ? ` (重叠 ${data.overlap_pixels || 0} / 标准 ${standardPixels} 像素)`
    : ` (检测 ${detectedPixels} / 标准 ${standardPixels} 像素)`) : '';
  const coverageWarning = data.decision_mode !== 'separated-v2' && coverage < coverageThreshold ? ' ⚠️ 低于' + (coverageThreshold * 100).toFixed(0) + '%阈值' : '';
  document.getElementById(`${prefix}-coverage-detail`).innerHTML =
    `<strong style="color:${data.decision_mode === 'separated-v2' ? '#6b7280' : (coverage < coverageThreshold ? '#dc2626' : '#059669')}">${coveragePercent}</strong>${pixelInfo}${coverageWarning}`;



  if (data.integrity) {
    const m = data.integrity;
    const el = document.getElementById(`${prefix}-coverage-detail`);
    const details = document.createElement('div');
    details.textContent = `面积比 ${(m.area_ratio * 100).toFixed(1)}% · 对齐后缺损 ${(m.missing_ratio * 100).toFixed(1)}% · 超出 ${(m.excess_ratio * 100).toFixed(1)}% · ${data.fragment_count ?? 1} 个连通区域`;
    el.appendChild(details);
  }

  // 位置偏移
  const offsetMm = data.offset_distance_mm || 0;
  const offsetPx = data.offset_distance_px || 0;
  const offsetMmX = Number(data.offset_x_mm || 0);
  const offsetMmY = Number(data.offset_y_mm || 0);
  const offsetPxX = Number(data.offset_x_px || 0);
  const offsetPxY = Number(data.offset_y_px || 0);
  const offsetDetail = ` (${offsetPxX > 0 ? '+' : ''}${offsetPxX.toFixed(1)}px, ${offsetPxY > 0 ? '+' : ''}${offsetPxY.toFixed(1)}px)`;

  if (!data.is_present || !data.alignment_metric) {
    document.getElementById(`${prefix}-offset-detail`).innerHTML =
      '<strong style="color:#dc2626;">无法确认（泡棉不存在或覆盖不足）</strong>';
  } else if (data.alignment_metric === 'mm' && maxOffsetMm !== null && maxOffsetMm !== undefined) {
    const exceeded = Math.abs(offsetMmX) > maxOffsetXMm || Math.abs(offsetMmY) > maxOffsetYMm;
    const warning = exceeded ? ` ⚠️ 限值 X±${Number(maxOffsetXMm).toFixed(1)} / Y±${Number(maxOffsetYMm).toFixed(1)}mm` : '';
    document.getElementById(`${prefix}-offset-detail`).innerHTML =
      `<strong style="color:${exceeded ? '#dc2626' : '#059669'}">X ${offsetMmX >= 0 ? '+' : ''}${offsetMmX.toFixed(2)} mm · Y ${offsetMmY >= 0 ? '+' : ''}${offsetMmY.toFixed(2)} mm</strong>${offsetDetail}${warning}`;
  } else if (data.alignment_metric === 'px') {
    const exceeded = Math.abs(offsetPxX) > maxOffsetXPx || Math.abs(offsetPxY) > maxOffsetYPx;
    const warning = exceeded ? ` ⚠️ 限值 X±${Number(maxOffsetXPx).toFixed(0)} / Y±${Number(maxOffsetYPx).toFixed(0)}px` : '';
    document.getElementById(`${prefix}-offset-detail`).innerHTML =
      `<strong style="color:${exceeded ? '#dc2626' : '#059669'}">X ${offsetPxX >= 0 ? '+' : ''}${offsetPxX.toFixed(1)} px · Y ${offsetPxY >= 0 ? '+' : ''}${offsetPxY.toFixed(1)} px</strong>${warning}`;
  } else if (offsetPxX !== 0 || offsetPxY !== 0 || offsetMm > 0) {
    // 相对ROI中心的偏移数据
    const displayOffset = offsetMm > 0 ? `${offsetMm.toFixed(2)} mm` : `${offsetPx.toFixed(1)} px`;
    document.getElementById(`${prefix}-offset-detail`).innerHTML =
      `<strong style="color:#6b7280;">${displayOffset}</strong>${offsetDetail}`;
  } else {
    // 完全无偏移数据
    document.getElementById(`${prefix}-offset-detail`).innerHTML =
      `<span style="color:#9ca3af;">-</span>`;
  }

}

// ── 获取缺陷原因（新增）────────────────────────────────────
function getDefectReason(data) {
  if (!data) return '未检测';
  if (data.inspection_status === 'INVALID') return '图像或测量不可靠';
  const reasons = {area_below_minimum: '面积不足', area_above_maximum: '面积异常偏大',
    incomplete: '形状缺损', excess_area: '超出标准区域', local_defect: '局部缺损',
    misaligned: '位置偏移', coverage_below_threshold: '原位置覆盖不足',
    no_foam_detected: '未找到泡棉'};
  if (data.quality_failures?.length) return data.quality_failures.map(k => reasons[k] || k).join('、');
  if (data.detected_pixels > 0 && data.is_complete === false) return '覆盖不足';
  if (!data.is_present) {
    const coverage = data.coverage_ratio || 0;
    if (coverage < 0.05) {
      return '不存在';
    } else {
      return '覆盖不足';
    }
  }
  if (!data.is_aligned) return '位置偏移';
  return '未知';
}

// ── 获取单侧问题描述（新增）────────────────────────────────
function getSideIssue(data) {
  if (!data || data.is_present && data.is_aligned && data.is_complete !== false) return '';
  if (data.quality_failures?.length) return getDefectReason(data);
  if (data.is_present && data.is_complete === false) return `覆盖不足(${(data.coverage_ratio * 100).toFixed(1)}%)`;

  const issues = [];
  if (!data.is_present) {
    const coverage = data.coverage_ratio || 0;
    if (coverage < 0.05) {
      issues.push('不存在');
    } else {
      issues.push(`覆盖不足(${(coverage * 100).toFixed(1)}%)`);
    }
  }
  if (!data.is_aligned) issues.push('位置偏移');

  return issues.join('、');
}

// ── 同步结果配方到左侧预览 ─────────────────────────────────────
function syncResultRecipeToPreview(result) {
  // 如果结果中包含使用的配方信息，同步到左侧预览
  if (result.recipe) {
    console.log('同步检测结果使用的配方到左侧预览:', result.recipe);

    // 更新左侧预览的ROI框，使其与检测时使用的配方完全一致
    if (result.recipe.roi_config) {
      applyRecipeRoiToOverlay(result.recipe);
    }

    // 如果当前POS与结果POS不同，可以选择是否更新（这里保持不变，只更新ROI显示）
    console.log('左侧预览ROI已同步到检测时使用的配方 POS', result.recipe.pos);
  }
}

function setMetricCard(cardId, valId, isOk, label, icon) {
  const card = document.getElementById(cardId);
  const val  = document.getElementById(valId);
  const iconEl = card.querySelector('.metric-icon');
  card.className = 'metric-card ' + (isOk ? 'ok' : 'ng');
  val.textContent = label;
  if (iconEl) iconEl.textContent = icon + (isOk ? '✓' : '✗');
}

function formatDefect(dt) {
  const map = { NONE: '无缺陷', MISSING: '泡棉缺失/漏贴', MISALIGNED: '位置偏移', LIFTED_EDGE: '边缘起翘' };
  return map[dt] || dt;
}

// ── 配方加载（简化版，仅用于 ROI 显示） ───────────────────
async function loadRecipes() {
  try {
    const query = new URLSearchParams({recipe_type: 'FOAM_2D'});

    const res = await fetch(`${API.recipes}?${query.toString()}`);
    const data = await res.json();
    if (data.success) {
      foam2DRecipes = data.recipes || [];
      const requestedRecipe = foam2DRecipes.find(item => String(item.id) === WORKBENCH_RECIPE_ID);
      selectedRecipeForEdit = requestedRecipe || (foam2DRecipes.length === 1 ? foam2DRecipes[0] : null);
      if (requestedRecipe) {
        document.getElementById('pos-index').value = requestedRecipe.pos ?? 0;
        if (!FOAM_RECIPE_EDITING) manualSelectedRecipe = requestedRecipe;
      }
      if (FOAM_RECIPE_EDITING) {
        const nameInput = document.getElementById('foam-recipe-draft-name');
        const remarkInput = document.getElementById('foam-recipe-draft-remark');
        renderFoamRecipeSelect();
        if (nameInput && selectedRecipeForEdit) nameInput.value = selectedRecipeForEdit.name || '';
        if (remarkInput && selectedRecipeForEdit) remarkInput.value = selectedRecipeForEdit.remark || '';
      }
      updateRecipeState();
      refreshPreviewRecipeRoi();
    }
  } catch (_) {
    foam2DRecipes = [];
    updateRecipeState();
    document.getElementById('foam-parameter-summary').textContent = '配方加载失败，请刷新页面重试';
  }
}

function renderFoamRecipeSelect() {
  const recipeSelect = document.getElementById('foam-recipe-select');
  if (!recipeSelect) return;
  recipeSelect.replaceChildren(new Option('请选择配方（新增和复制请到配方页面）', ''));
  foam2DRecipes.forEach(recipe => {
    recipeSelect.add(new Option(
      `${recipe.name}${recipe.is_active ? '' : '（未启用）'}`,
      String(recipe.id),
    ));
  });
  recipeSelect.value = selectedRecipeForEdit ? String(selectedRecipeForEdit.id) : '';
}

function selectFoamRecipeForEdit(recipeId) {
  const recipe = foam2DRecipes.find(item => String(item.id) === String(recipeId)) || null;
  selectedRecipeForEdit = recipe;
  manualSelectedRecipe = null;
  cal.dirty = false;
  cal.rois = {};
  const nameInput = document.getElementById('foam-recipe-draft-name');
  const remarkInput = document.getElementById('foam-recipe-draft-remark');
  const stateBadge = document.getElementById('foam-recipe-save-state');
  if (recipe) {
    document.getElementById('pos-index').value = recipe.pos ?? 0;
    if (nameInput) nameInput.value = recipe.name || '';
    if (remarkInput) remarkInput.value = recipe.remark || '';
    if (stateBadge) {
      stateBadge.textContent = recipe.is_active ? '已发布 · 可修改' : '草稿 · 可修改';
      stateBadge.classList.toggle('saved', Boolean(recipe.is_active));
    }
    applyRecipeRoiToOverlay(recipe);
    loadStandardRoiStatus(recipe.id);
  } else {
    if (nameInput) nameInput.value = '新建泡棉检测配方';
    if (remarkInput) remarkInput.value = '';
    if (stateBadge) {
      stateBadge.textContent = '新草稿';
      stateBadge.classList.remove('saved');
    }
    renderRoiBoxes();
    updateStandardRoiPanel({ready:false, reason:'请先保存配方', sides:{}});
  }
  recipeValidationCompleted = false;
  updateRecipeState();
}

// ── 更新配方参数和ROI 状态 ─────────────────────────────────────────
function fillFoamQualitySettings(recipe) {
  const summary = recipe?.foam_summary || {};
  document.getElementById('foam-parameter-summary').textContent = recipe
    ? '整架所有检测位置共用'
    : '请选择配方查看参数';
  const values = document.getElementById('foam-parameter-values');
  values.replaceChildren();
  values.hidden = !recipe;
  if (recipe) {
    const rows = [
      ['泡棉与分割', `${summary.material_label || '未标注颜色'} · ${summary.segmentation_label || '—'}`],
      ...foamDecisionSummary(recipe),
    ];
    for (const [label, content] of rows) {
      const term = document.createElement('dt');
      const value = document.createElement('dd');
      term.textContent = label;
      value.textContent = content;
      values.append(term, value);
    }
  }
  document.getElementById('foam-edit-parameters').href = '/vision/recipes/?tab=foam2d' + (recipe ? `&edit=${recipe.id}` : '');
}

function updateRecipeState() {
  const recipe = currentDetectionRecipe();
  fillFoamQualitySettings(recipe);
  currentStandardRoiReady = Boolean(recipe?.standard_template_status?.ready);
  if (recipe) loadStandardRoiStatus(recipe.id);
}

function upsertSavedRecipe(savedRecipe) {
  if (!savedRecipe) return;
  const normalizedRecipe = {
    ...savedRecipe,
    pos: Number(savedRecipe.pos ?? currentPOS()),
  };
  const index = foam2DRecipes.findIndex(recipe => Number(recipe.id) === Number(normalizedRecipe.id));
  if (index >= 0) {
    foam2DRecipes.splice(index, 1, normalizedRecipe);
  } else {
    foam2DRecipes.push(normalizedRecipe);
  }
  selectedRecipeForEdit = normalizedRecipe;
  renderFoamRecipeSelect();
  if (Number(normalizedRecipe.pos) === currentPOS()) {
    manualSelectedRecipe = null;
  }
}

function showRecipeSaveSuccess(recipe, leftFoamROI, rightFoamROI) {
  const status = document.getElementById('calibration-status');
  if (!status) return;
  const pos = recipe?.pos ?? currentPOS();
  const formatRoiInfo = (roi) => {
    if (!roi) return '未设置';
    if (roi.type === 'polygon' && roi.points) return `多边形 (${roi.points.length}个顶点)`;
    return `x=${roi.x || 0}, y=${roi.y || 0}`;
  };
  status.textContent =
    '✅ 整架共用配方已保存' +
    '；左ROI: ' + formatRoiInfo(leftFoamROI) +
    '；右ROI: ' + formatRoiInfo(rightFoamROI);
}

// ── 保存配方到指定 POS ───────────────────────────────────────
async function saveRoiToRecipe(targetPos, saveMode = 'publish') {
  // 查找已有配方
  const existingRecipe = currentDetectionRecipe();
  if (!existingRecipe?.id) { showPublishFeedback('请先在配方页面新建或复制配方，再选择配方绘制 ROI。'); return; }

  let leftFoamROI = null;
  let rightFoamROI = null;

  // 使用当前预览图的实际尺寸；如果图片尚未加载则降级到 1280×720
  const previewImg = document.getElementById('preview-image');
  const imageWidth  = previewImg?.naturalWidth || existingRecipe?.image_width || 1280;
  const imageHeight = previewImg?.naturalHeight || existingRecipe?.image_height || 720;

  if (cal.rois.left && cal.rois.right) {
    const buildRoiObj = (roiData) => {
      // 新格式：多边形
      if (roiData.type === 'polygon') {
        return {
          type: 'polygon',
          points: roiData.points, // [ [x, y], ... ] 比例坐标
        };
      }
      // 老格式：矩形 [lx1, ly1, lx2, ly2]
      const [x1, y1, x2, y2] = roiData;
      return {
        x1r: x1, y1r: y1, x2r: x2, y2r: y2,           // 比例坐标（主）
        x: Math.round(x1 * imageWidth),                    // 像素坐标（参考）
        y: Math.round(y1 * imageHeight),
        width:  Math.round((x2 - x1) * imageWidth),
        height: Math.round((y2 - y1) * imageHeight)
      };
    };
    leftFoamROI = buildRoiObj(cal.rois.left);
    rightFoamROI = buildRoiObj(cal.rois.right);
  } else if (existingRecipe && existingRecipe.roi_config && existingRecipe.roi_config.leftFoamROI && existingRecipe.roi_config.rightFoamROI) {
    // 回退到配方原有的 ROI 配置（如果存在）
    leftFoamROI = existingRecipe.roi_config.leftFoamROI;
    rightFoamROI = existingRecipe.roi_config.rightFoamROI;
  }

  // 验证 ROI 是否已标定
  if (!leftFoamROI || !rightFoamROI) {
    alert('❌ 请先标定左右泡棉 ROI\n\n操作步骤：\n1. 选择"左侧泡棉"\n2. 在预览图上拖拽框选左侧区域\n3. 选择"右侧泡棉"\n4. 拖拽框选右侧区域\n5. 然后点击保存');
    return;
  }

  console.log('开始保存配方到 POS', targetPos);
  console.log('左侧 ROI (像素):', leftFoamROI);
  console.log('右侧 ROI (像素):', rightFoamROI);
  if (!Array.isArray(cal.rois.layer) && !(cal.rois.layer?.type === 'polygon' && cal.rois.layer.points?.length >= 3)) {
    alert('请框选“本层搜索大框”，包含左右标准泡棉并留出偏移搜索空间。');
    return;
  }
  const layerPolygon = cal.rois.layer.type === 'polygon';
  const [lx1, ly1, lx2, ly2] = layerPolygon ? [0,0,0,0] : cal.rois.layer;
  const layerSearchROI = layerPolygon ? cal.rois.layer : {x1r: lx1, y1r: ly1, x2r: lx2, y2r: ly2, x: Math.round(lx1 * imageWidth), y: Math.round(ly1 * imageHeight),
    width: Math.round((lx2-lx1)*imageWidth), height: Math.round((ly2-ly1)*imageHeight)};
  const productAnchors = ['body1','body2'].map((key,index) => {
    const box = cal.rois[key];
    if (!box) return existingRecipe?.roi_config?.productAnchorROIs?.[index] || null;
    if (!Array.isArray(box)) return null;
    return {x1r:box[0],y1r:box[1],x2r:box[2],y2r:box[3]};
  }).filter(Boolean);
  const payload = {
    simple_save: FOAM_RECIPE_EDITING,
    preview_capture_token: FOAM_RECIPE_EDITING && !pendingFile ? lastCameraCaptureToken : '',
    id: existingRecipe?.id,
    shared_recipe: true,
    pos: targetPos,

    camera_side: 'both',
    image_width: imageWidth,    // 保存时图片的实际尺寸（供旧格式解析参考）
    image_height: imageHeight,
    roi_config: {
      ...(existingRecipe.roi_config || {}),
      leftFoamROI,
      rightFoamROI,
      layerSearchROI,
      productAnchorROIs: productAnchors
    },
    roi_only: true,

  };

  if (FOAM_RECIPE_EDITING && !cal.dirty && existingRecipe?.roi_config
      && Number(existingRecipe.image_width) === imageWidth
      && Number(existingRecipe.image_height) === imageHeight) {
    payload.roi_config = existingRecipe.roi_config;
  }
  console.log('发送保存请求:', payload);

  showLoading('保存配方中...');
  try {
    const form = new FormData();
    form.append('payload', JSON.stringify(payload));
    if (FOAM_RECIPE_EDITING && pendingFile) form.append('image', pendingFile);
    const response = await fetch(API.saveRecipe, {
      method: 'POST', headers: {'X-CSRFToken': getCsrf()}, body: form
    });

    console.log('响应状态:', response.status);

    if (!response.ok) {
      const failure = await response.json().catch(() => ({}));
      throw new Error(failure.error || `HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    console.log('响应数据:', data);

    if (data.success) {
      const savedRecipe = data.recipe || payload;
      upsertSavedRecipe(savedRecipe);
      selectedRecipeForEdit = foam2DRecipes.find(recipe => Number(recipe.id) === Number(savedRecipe.id)) || savedRecipe;
      renderFoamRecipeSelect();
      const positionModal = document.getElementById('pos-selector-modal');
      if (positionModal) positionModal.style.display = 'none';
      // 保存成功后清除 dirty，同步 cal.rois 为刚保存的 ROI
      cal.dirty = false;
      if (savedRecipe?.roi_config) {
        const l = savedRecipe.roi_config.leftFoamROI;
        const r = savedRecipe.roi_config.rightFoamROI;
        if (l) cal.rois.left  = roiToRatio(l, savedRecipe);
        if (r) cal.rois.right = roiToRatio(r, savedRecipe);
        if (savedRecipe.roi_config.layerSearchROI) {
          cal.rois.layer = roiToRatio(savedRecipe.roi_config.layerSearchROI, savedRecipe);
        }
      }
      updateRecipeState();
      renderRoiBoxes();  // 直接重绘，不覆盖 cal.rois
      showRecipeSaveSuccess(savedRecipe, leftFoamROI, rightFoamROI);
      showPublishFeedback('标准 ROI 与参数已保存，配方参数和启停状态保持不变。', false);
      currentStandardRoiReady = Boolean(savedRecipe.standard_template_status?.ready);
      const recipeState = document.getElementById('foam-recipe-save-state');
      if (recipeState) {
        recipeState.textContent = 'ROI 配置已保存';
        recipeState.classList.toggle('saved', saveMode === 'publish');
      }
    } else {
      const errorMsg = data.error || '未知错误';
      showPublishFeedback('保存失败：' + errorMsg);
      console.error('保存失败:', errorMsg);
      alert(`❌ 保存失败\n\n错误信息: ${errorMsg}\n\n请检查：\n1. 网络连接是否正常\n2. 服务器是否运行\n3. 浏览器控制台是否有错误`);
    }
  } catch (error) {
    showPublishFeedback('保存失败：' + error.message);
    console.error('配方保存失败:', error);
    if (!FOAM_RECIPE_EDITING) alert('保存失败：' + error.message);
  } finally {
    hideLoading();
  }
}

// ── 临时配方选择器 ───────────────────────────────────────────
function showTempRecipeSelector() {
  const modal = document.getElementById('temp-recipe-modal');
  const list = document.getElementById('temp-recipe-list');

  if (foam2DRecipes.length === 0) {
    alert('暂无可用配方');
    return;
  }

  list.innerHTML = foam2DRecipes.map(recipe => {
    const left = recipe.roi_config?.leftFoamROI || {};
    const right = recipe.roi_config?.rightFoamROI || {};
    return `
      <button class="btn-select-temp-recipe" data-recipe-id="${recipe.id}">
        <strong>POS ${recipe.pos} - ${recipe.name}</strong>
        <div class="recipe-roi-preview">
          左: ${left.type === 'polygon' ? '多边形' : `x=${left.x || 0}, y=${left.y || 0}`} | 右: ${right.type === 'polygon' ? '多边形' : `x=${right.x || 0}, y=${right.y || 0}`}
        </div>
      </button>
    `;
  }).join('');

  modal.style.display = 'flex';
}



// ── ROI 标定 ─────────────────────────────────────────────
// dirty=true 表示用户已手动画过 ROI，refreshPreviewRecipeRoi 不应覆盖
const cal = { rois: {}, drawing: false, start: null, dirty: false, drawMode: 'rect', currentPoints: [] };

function getImgRect() {
  const img = document.getElementById('preview-image');
  if (!img || img.style.display === 'none') return null;
  return img.getBoundingClientRect();
}

function renderRoiBoxes() {
  const overlay = document.getElementById('roi-overlay');
  overlay.querySelectorAll('.roi-box').forEach(b => b.remove());

  const img = document.getElementById('preview-image');
  if (!img || img.style.display === 'none') return;

  const canvas = document.getElementById('roi-canvas');
  if (canvas) {
    // Resize canvas to match the overlay exactly
    canvas.width = overlay.clientWidth;
    canvas.height = overlay.clientHeight;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  const overlayRect = overlay.getBoundingClientRect();
  const imgRect     = img.getBoundingClientRect();

  const imgOffsetLeft = imgRect.left - overlayRect.left;
  const imgOffsetTop  = imgRect.top  - overlayRect.top;
  const displayWidth  = imgRect.width;
  const displayHeight = imgRect.height;

  // 如果正在画多边形，先画出当前正在绘制的线
  if (cal.drawing && cal.drawMode === 'freehand' && cal.currentPoints.length > 0 && canvas) {
    const ctx = canvas.getContext('2d');
    ctx.beginPath();
    cal.currentPoints.forEach((pt, i) => {
      const x = imgOffsetLeft + pt[0] * displayWidth;
      const y = imgOffsetTop + pt[1] * displayHeight;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    const side = document.getElementById('calibration-side').value;
    ctx.strokeStyle = side === 'left' ? '#3b82f6' : '#10b981';
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  Object.entries(cal.rois).forEach(([side, roiData]) => {
    if (!roiData) return;
    if (roiData.type === 'polygon' && canvas) {
      // Draw polygon
      const points = roiData.points;
      if (points && points.length > 0) {
        const ctx = canvas.getContext('2d');
        ctx.beginPath();
        points.forEach((pt, i) => {
          const x = imgOffsetLeft + pt[0] * displayWidth;
          const y = imgOffsetTop + pt[1] * displayHeight;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.closePath();

        ctx.fillStyle = side === 'left' ? 'rgba(59,130,246,0.1)' : 'rgba(16,185,129,0.1)';
        ctx.fill();
        ctx.strokeStyle = side === 'left' ? '#3b82f6' : '#10b981';
        ctx.lineWidth = 2;
        ctx.stroke();

        // Draw label at the first point
        if (points.length > 0) {
           const label = document.createElement('div');
           label.className = 'roi-box-label';
           label.textContent = ({layer:'本层搜索区域',left:'左标准位置',right:'右标准位置',body1:'产品基准区 1',body2:'产品基准区 2'})[side];
           // Reusing roi-box styling to make label look similar
           const dummyBox = document.createElement('div');
           dummyBox.className = `roi-box ${side}`;
           dummyBox.style.border = 'none';
           dummyBox.style.background = 'none';
           dummyBox.style.left = `${imgOffsetLeft + points[0][0] * displayWidth}px`;
           dummyBox.style.top = `${imgOffsetTop + points[0][1] * displayHeight}px`;
           dummyBox.style.width = '0px';
           dummyBox.style.height = '0px';

           label.style.top = '-20px';
           dummyBox.appendChild(label);
           overlay.appendChild(dummyBox);
        }
      }
    } else if (Array.isArray(roiData) && roiData.length === 4) {
      // Draw rect
      const [x1r, y1r, x2r, y2r] = roiData;
      const box = document.createElement('div');
      box.className = `roi-box ${side}`;

      box.style.left   = `${imgOffsetLeft + x1r * displayWidth}px`;
      box.style.top    = `${imgOffsetTop  + y1r * displayHeight}px`;
      box.style.width  = `${(x2r - x1r) * displayWidth}px`;
      box.style.height = `${(y2r - y1r) * displayHeight}px`;

      const label = document.createElement('div');
      label.className = 'roi-box-label';
      label.textContent = ({layer:'本层搜索区域',left:'左标准位置',right:'右标准位置',body1:'产品基准区 1',body2:'产品基准区 2'})[side];
      box.appendChild(label);
      overlay.appendChild(box);
    }
  });
}

function ptrToRatio(e) {
  // ✅ 统一坐标系修复：直接使用 img.getBoundingClientRect() 视口坐标系
  // 鼠标坐标 e.clientX/clientY 也是视口坐标，两者减法即为图片内相对坐标
  // 无论页面是否滚动、flex 布局如何居中，都能精准定位
  const img = document.getElementById('preview-image');
  if (!img || img.style.display === 'none') return null;

  const imgRect = img.getBoundingClientRect();

  return [
    Math.max(0, Math.min(1, (e.clientX - imgRect.left) / imgRect.width)),
    Math.max(0, Math.min(1, (e.clientY - imgRect.top)  / imgRect.height)),
  ];
}

function startCalibration(mode) {
  const overlay = document.getElementById('roi-overlay');

  // 如果当前是其它模式正在标定，先关闭再开启新模式
  if (overlay.classList.contains('calibrating') && cal.drawMode !== mode) {
     overlay.classList.remove('calibrating');
  }

  const active = overlay.classList.toggle('calibrating');
  cal.drawMode = mode;
  const side = document.getElementById('calibration-side').value;
  if (side.startsWith('body')) { mode = 'rect'; cal.drawMode = 'rect'; }

  if (active) {
    // 进入绘制模式：如果 cal.rois 某侧为空，先从配方预填，让用户可以在原位置微调
    const recipe = currentDetectionRecipe();
    if (recipe?.roi_config) {
      const left = recipe.roi_config.leftFoamROI;
      const right = recipe.roi_config.rightFoamROI;
      if (left && !cal.rois.left) {
         cal.rois.left = left.type === 'polygon' ? left : roiToRatio(left, recipe);
      }
      if (right && !cal.rois.right) {
         cal.rois.right = right.type === 'polygon' ? right : roiToRatio(right, recipe);
      }
      renderRoiBoxes();
    }
    const modeName = mode === 'rect' ? '拖拽框选' : '按住鼠标沿边缘描画，松开后自动闭合';
    document.getElementById('calibration-status').textContent =
      `请在预览图上${modeName}【${({layer:'本层搜索大框',left:'左侧标准泡棉',right:'右侧标准泡棉',body1:'产品基准区 1',body2:'产品基准区 2'})[side]}】区域（可在现有框上重画）`;
  } else {
    document.getElementById('calibration-status').textContent = '';
  }
}

document.getElementById('btn-start-roi').addEventListener('click', () => startCalibration('rect'));
document.getElementById('btn-start-roi-polygon').addEventListener('click', () => startCalibration('freehand'));

document.getElementById('roi-overlay').addEventListener('mousedown', e => {
  if (!e.currentTarget.classList.contains('calibrating')) return;
  const pt = ptrToRatio(e);
  if (!pt) return;
  cal.drawing = true;
  cal.start   = pt;
  if (cal.drawMode === 'freehand') {
    cal.currentPoints = [pt];
  }
});
document.getElementById('roi-overlay').addEventListener('mousemove', e => {
  if (!cal.drawing || !cal.start) return;
  const cur  = ptrToRatio(e);
  if (!cur) return;
  const side = document.getElementById('calibration-side').value;

  if (cal.drawMode === 'rect') {
    const [sx, sy] = cal.start, [cx, cy] = cur;
    cal.rois[side] = [Math.min(sx,cx), Math.min(sy,cy), Math.max(sx,cx), Math.max(sy,cy)];
  } else if (cal.drawMode === 'freehand') {
    cal.currentPoints.push(cur);
  }
  renderRoiBoxes();
});
document.getElementById('roi-overlay').addEventListener('mouseup', () => {
  if (cal.drawing) {
    if (cal.drawMode === 'freehand' && cal.currentPoints.length > 2) {
      const side = document.getElementById('calibration-side').value;
      cal.rois[side] = { type: 'polygon', points: cal.currentPoints };
    }
    cal.dirty = true;  // 用户完成一次绘制，标记为 dirty，防止配方刷新覆盖
  }
  cal.drawing = false;
  cal.start = null;
  cal.currentPoints = [];
  renderRoiBoxes();
});

document.getElementById('btn-save-roi').addEventListener('click', async () => {
  if (cal.rois.layer || FOAM_RECIPE_EDITING) { document.getElementById('btn-save-recipe').click(); return; }
  if (!cal.rois.left || !cal.rois.right) {
    alert('请先分别框选左侧和右侧泡棉 ROI，再保存标定！');
    return;
  }
  const pos = Number(document.getElementById('pos-index').value || 0);
  showLoading('保存 ROI 标定...');
  try {
    const res = await fetch(API.saveCalibration, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        position_index: pos,
        left:  cal.rois.left,
        right: cal.rois.right,
        thresholds: { coverage_threshold: 0.3, require_dark_support: true },
      }),
    });
    const data = await res.json();
    if (data.success) {
      document.getElementById('calibration-status').textContent = '✅ ROI 已保存，后续检测自动复用';
      document.getElementById('roi-overlay').classList.remove('calibrating');
    } else {
      alert('保存失败：' + (data.error || '未知错误'));
    }
  } catch (e) {
    alert('网络请求失败：' + e.message);
  } finally {
    hideLoading();
  }
});

// ── 初始化：加载已有标定 ─────────────────────────────────
async function loadCalibration() {
  try {
    const res  = await fetch(API.calibration);
    const data = await res.json();
    const pos  = document.getElementById('pos-index').value || '0';
    const rois = data.profile?.foam_rois?.[pos] || {};
    if (rois.left)  cal.rois.left  = rois.left;
    if (rois.right) cal.rois.right = rois.right;
    if (cal.rois.left || cal.rois.right) {
      document.getElementById('calibration-status').textContent = '已加载上次 ROI 标定';
    }
    refreshPreviewRecipeRoi();
  } catch (_) { /* 标定可选，不影响使用 */ }
}

document.addEventListener('DOMContentLoaded', () => {
  // 注入 CSRF
  if (!document.querySelector('[name=csrfmiddlewaretoken]')) {
    const inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = 'csrfmiddlewaretoken'; inp.value = 'test';
    document.body.appendChild(inp);
  }
  if (FOAM_RECIPE_EDITING) {
    const toolsHost = document.getElementById('foam-recipe-tools-host');
    const calibrationPanel = document.querySelector('.roi-calibration-panel');
    if (toolsHost && calibrationPanel) toolsHost.appendChild(calibrationPanel);
    const captureButton = document.getElementById('btn-capture-inspect');
    document.getElementById('btn-refresh-preview').textContent = '拍照取图';
    document.getElementById('btn-save-recipe').textContent = '保存配方（ROI 标准区域）';
    document.querySelector('.roi-head').textContent = '检测区域 · 矩形或不规则区域';
    document.querySelector('.pos-hint').textContent = '0 = 第1层，1 = 第2层，2 = 第3层';
    document.querySelector('#camera-placeholder p').textContent = '拍照或导入一张合格样件图，然后绘制三个 ROI 框';
    const tools = document.querySelector('.roi-tools');
    const modeLabel = document.createElement('label');
    modeLabel.textContent = '绘制方式 ';
    const modeSelect = document.createElement('select');
    modeSelect.id = 'simple-roi-draw-mode';
    modeSelect.innerHTML = '<option value="rect">矩形框</option><option value="freehand">画笔 · 不规则区域</option>';
    modeLabel.appendChild(modeSelect);
    tools.before(modeLabel);
    modeSelect.addEventListener('change', () => {
      document.getElementById('roi-overlay').classList.remove('calibrating');
      startCalibration(document.getElementById('calibration-side').value.startsWith('body') ? 'rect' : modeSelect.value);
    });
    const choices = document.createElement('div');
    choices.className = 'simple-roi-choices';
    const advanced = document.createElement('details');
    advanced.style.cssText = 'width:100%;margin-top:8px;';
    advanced.innerHTML = '<summary style="cursor:pointer;">高级：产品位移补偿（可选）</summary><p class="page-hint">仅在配方启用产品位移补偿时使用。在产品本体上框选两个稳定特征，避开泡棉且互不重叠，用于校正产品摆放偏移。基准区必须使用矩形；普通检测无需绘制。</p>';
    const anchorChoices = document.createElement('div');
    anchorChoices.className = 'simple-roi-choices';
    advanced.appendChild(anchorChoices);
    [['left','① 左标准框'],['right','② 右标准框'],['layer','③ 本层大框'],['body1','④ 产品基准 1'],['body2','⑤ 产品基准 2']].forEach(([side,label]) => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'btn btn-secondary'; button.textContent = label;
      button.addEventListener('click', () => {
        document.getElementById('calibration-side').value = side;
        document.getElementById('roi-overlay').classList.remove('calibrating');
        startCalibration(side.startsWith('body') ? 'rect' : modeSelect.value);
        [choices, anchorChoices].forEach(group => group.querySelectorAll('button').forEach(item => item.classList.toggle('selected', item === button)));
      });
      (side.startsWith('body') ? anchorChoices : choices).appendChild(button);
    });
    tools.prepend(choices);
    choices.after(advanced);
    const saveActions = document.getElementById('foam-recipe-save-actions');
    saveActions.appendChild(document.getElementById('btn-save-recipe'));
    saveActions.appendChild(document.getElementById('recipe-publish-feedback'));
    ['foam-recipe-draft-name', 'foam-recipe-draft-remark'].forEach(id => {
      document.getElementById(id)?.addEventListener('input', () => {
        const state = document.getElementById('foam-recipe-save-state');
        if (state) {
          state.textContent = '有未保存修改';
          state.classList.remove('saved');
        }
      });
    });
    document.getElementById('foam-recipe-select')?.addEventListener('change', event => {
      selectFoamRecipeForEdit(event.target.value);
    });
  }

  // POS only labels results; the selected rack recipe and teaching ROIs stay fixed.
  document.getElementById('pos-index')?.addEventListener('change', () => {
    updateRecipeState();
  });
  document.getElementById('preview-image').addEventListener('load', () => {
    refreshPreviewRecipeRoi();
  });
  window.addEventListener('resize', () => {
    refreshPreviewRecipeRoi();
  });

  function ensureRecipeRois() {
    // 允许只重画一侧：缺失的一侧自动从当前配方补全
    const recipe = currentDetectionRecipe();
    if (!cal.rois.left && recipe?.roi_config?.leftFoamROI) {
      const l = recipe.roi_config.leftFoamROI;
      cal.rois.left = l.type === 'polygon' ? l : roiToRatio(l, recipe);
    }
    if (!cal.rois.right && recipe?.roi_config?.rightFoamROI) {
      const r = recipe.roi_config.rightFoamROI;
      cal.rois.right = r.type === 'polygon' ? r : roiToRatio(r, recipe);
    }
    if (!cal.rois.left || !cal.rois.right) {
      alert('请先框选左侧和右侧泡棉 ROI\n\n提示：点击"框选 ROI"后在预览图上拖拽绘制');
      return false;
    }
    return true;
  }

  // 保存配方按钮
  document.getElementById('btn-save-recipe')?.addEventListener('click', async () => {
    if (!ensureRecipeRois()) return;
    if (FOAM_RECIPE_EDITING) {
      const button = document.getElementById('btn-save-recipe');
      button.disabled = true;
      button.textContent = '保存中…';
      try { await saveRoiToRecipe(currentPOS(), 'publish'); }
      finally { button.disabled = false; button.textContent = '保存配方（ROI 标准区域）'; }
    } else {
      document.getElementById('pos-selector-modal').style.display = 'flex';
    }
  });

  document.getElementById('btn-publish-recipe')?.addEventListener('click', async () => {
    const button = document.getElementById('btn-publish-recipe');
    showPublishFeedback('正在检查发布条件…', false);
    try {
      if (!cal.rois.left || !cal.rois.right) {
        showPublishFeedback('无法发布：请先绘制左右泡棉标准框，并保存草稿。');
        return;
      }
      if (!Array.isArray(cal.rois.layer) && !(cal.rois.layer?.type === 'polygon' && cal.rois.layer.points?.length >= 3)) {
        showPublishFeedback('无法发布：请先绘制“本层搜索大框”，包含左右标准框，并保存草稿。');
        return;
      }
      if (cal.dirty) {
        showPublishFeedback('无法发布：ROI 有未保存修改。请先保存草稿，再试跑验证。');
        return;
      }
      if (!currentStandardRoiReady) {
        const reason = document.getElementById('standard-roi-message')?.textContent || '标准 ROI 未配置';
        showPublishFeedback('无法发布：' + reason + '。请绘制并保存左右标准 ROI，再拍照试跑验证。');
        return;
      }
      if (!recipeValidationCompleted) {
        showPublishFeedback('无法发布：当前配方尚未试跑通过。请点击“拍照试跑验证”，确认左右泡棉均合格后再发布。');
        return;
      }
      button.disabled = true;
      showPublishFeedback('正在发布配方…', false);
      await saveRoiToRecipe(currentPOS(), 'publish');
    } catch (error) {
      showPublishFeedback('发布失败：' + error.message);
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById('btn-refresh-roi')?.addEventListener('click', () => {
    loadStandardRoiStatus(currentDetectionRecipe()?.id);
  });

  // POS 选择对话框按钮
  document.querySelectorAll('.btn-pos').forEach(btn => {
    btn.addEventListener('click', () => {
      const pos = parseInt(btn.dataset.pos);
      saveRoiToRecipe(pos, 'publish');
    });
  });

  // 临时配方选择
  document.addEventListener('click', (e) => {
    if (e.target.closest('.btn-select-temp-recipe')) {
      const btn = e.target.closest('.btn-select-temp-recipe');
      const recipeId = parseInt(btn.dataset.recipeId);
      manualSelectedRecipe = foam2DRecipes.find(r => r.id === recipeId);
      updateRecipeState();
      applyRecipeRoiToOverlay(manualSelectedRecipe);
      document.getElementById('temp-recipe-modal').style.display = 'none';
    }
  });

  loadCalibration();
  loadRecipes();
});


// ── 历史记录选择弹窗逻辑 ──
let _allRecords = [];  // 已加载的全部记录
let _recordImportTarget = 'foam';

// 开启弹窗
async function openRecordsModal(target = 'foam') {
  _recordImportTarget = target;
  document.getElementById('records-modal-title').textContent = '从泡棉检测记录导入图片';
  document.getElementById('records-modal-guidance').textContent = '显示检测历史；有原图的记录可点击导入，缺图记录仍保留检测数据。';
  document.getElementById('records-modal-overlay').classList.add('active');
  await loadRecords();
}

// 关闭弹窗
function closeRecordsModal() {
  document.getElementById('records-modal-overlay').classList.remove('active');
}

// 从后端获取记录
async function loadRecords() {
  document.getElementById('records-modal-loading').style.display = 'block';
  document.getElementById('records-grid').innerHTML = '';
  document.getElementById('records-empty').style.display = 'none';
  try {
    const res = await fetch(API.inspectionRecords + '?limit=100');
    const data = await res.json();
    if (data.success) {
      _allRecords = data.records;
    } else {
      _allRecords = [];
    }
  } catch(e) {
    _allRecords = [];
  } finally {
    document.getElementById('records-modal-loading').style.display = 'none';
    renderRecords();
  }
}

// 渲染记录卡片
function renderRecords() {
  const search = (document.getElementById('records-search')?.value || '').toLowerCase();
  const passFilter = document.getElementById('records-filter-pass')?.value || 'all';

  let filtered = _allRecords.filter(r => {
    if (passFilter === 'pass' && !r.is_passed) return false;
    if (passFilter === 'fail' && r.is_passed) return false;
    if (search) {
      const haystack = `${r.created_at} POS${r.position_index} ${r.is_passed ? 'OK' : 'NG'}`.toLowerCase();
      if (!haystack.includes(search)) return false;
    }
    return true;
  });

  const grid = document.getElementById('records-grid');
  const emptyEl = document.getElementById('records-empty');
  const countEl = document.getElementById('records-count');

  countEl.textContent = `共 ${filtered.length} 条`;

  if (filtered.length === 0) {
    grid.innerHTML = '';
    emptyEl.style.display = 'block';
    return;
  }
  emptyEl.style.display = 'none';

  grid.innerHTML = filtered.map(r => {
    const statusCls = r.is_passed ? 'rc-pass' : 'rc-fail';
    const statusTxt = r.is_passed ? '✅ OK' : '❌ NG';
    const score = (r.score * 100).toFixed(0);
    const coverage = (r.coverage_ratio * 100).toFixed(1);
    const imgSrc = r.result_image_url || r.original_image_url;
    return `
      <div class="record-card" data-record-id="${r.id}"
           data-img-url="${r.original_image_url}"
           data-time="${r.created_at}"
           data-pos="${r.position_index}">
        ${imgSrc ? `<img src="${imgSrc}" alt="检测图" loading="lazy"
             onerror="this.style.background='#333';this.alt='图片加载失败';">` : '<div style="padding:32px 12px;text-align:center;">原图缺失 · 检测数据已保留</div>'}
        <div class="record-card-info">
          <div class="rc-time">${r.created_at}</div>
          <div class="rc-meta">
            <span class="${statusCls}">${statusTxt}</span>
            <span>POS ${r.position_index}</span>
            <span>覆盖率${coverage}%</span>
          </div>
        </div>
      </div>`;
  }).join('');

  // 绑定点击事件
  grid.querySelectorAll('.record-card').forEach(card => {
    card.addEventListener('click', () => selectRecordImage(card));
  });
}

// 选择历史记录中的图片
async function selectRecordImage(card) {
  const imgUrl = card.dataset.imgUrl;
  if (!imgUrl) { document.getElementById('records-modal-guidance').textContent = '这条记录的原图已缺失，无法导入；检测数据仍保留。'; return; }
  const time   = card.dataset.time;
  const pos    = card.dataset.pos;

  if (!imgUrl) {
    alert('该记录无原图文件可用。');
    return;
  }

  showLoading('加载记录图片...');
  try {
    // 通过 fetch 下载图片并转为 Blob / File
    const resp = await fetch(imgUrl);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const blob = await resp.blob();
    const filename = `记录_POS${pos}_${time.replace(/[: ]/g, '-')}.jpg`;
    const file = new File([blob], filename, { type: blob.type || 'image/jpeg' });

    // 显示在左侧预览区（与「导入图片」按钮相同效果）
    const dataUrl = URL.createObjectURL(blob);
    const img = document.getElementById('preview-image');
    img.src = dataUrl;
    img.style.display = 'block';
    document.getElementById('camera-placeholder').style.display = 'none';
    refreshPreviewRecipeRoi();

    // 暫存，等待「拍照检测」
    pendingFile = file;
    pendingFileDataUrl = dataUrl;
    setPendingBadge(`记录图片 POS${pos} (${time})`);
    updateCaptureButtonText();

    closeRecordsModal();
  } catch(e) {
    console.error('历史记录图片导入失败:', e);
    alert('图片加载失败：' + e.message);
  } finally {
    hideLoading();
  }
}

// 弹窗按钮监听
document.getElementById('btn-import-from-records').addEventListener('click', () => openRecordsModal('foam'));
document.getElementById('records-modal-close').addEventListener('click', closeRecordsModal);
document.getElementById('records-modal-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('records-modal-overlay')) closeRecordsModal();
});

// 搜索 / 过滤实时渲染
document.getElementById('records-search').addEventListener('input', renderRecords);
document.getElementById('records-filter-pass').addEventListener('change', renderRecords);

// Escape 键关闭弹窗
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeRecordsModal();
});

