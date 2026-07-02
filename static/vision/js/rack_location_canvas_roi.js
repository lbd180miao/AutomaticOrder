/**
 * 3D配方页面 Canvas ROI 绘制功能
 * 
 * 功能：
 * 1. 在深度伪彩图上绘制可拖拽的矩形ROI
 * 2. 将2D像素坐标转换为相机坐标系3D ROI
 * 3. 调用坐标转换API将相机ROI转换为机器人基坐标系ROI
 * 4. 自动填充到表单
 */

(function () {
  'use strict';

  // ============================================================================
  // 状态管理
  // ============================================================================
  
  const state = {
    isDrawing: false,
    startX: 0,
    startY: 0,
    currentROI: null,
    canvas: null,
    ctx: null,
    image: null,
    depthData: null, // 深度图数据（可选）
  };

  // 相机内参（简化的针孔模型，与 image_io.py 中的 PINHOLE_FX/FY 对应）
  const CAMERA_INTRINSICS = {
    fx: 600.0,  // 焦距 X
    fy: 600.0,  // 焦距 Y
    cx: 320.0,  // 主点 X (640/2)
    cy: 240.0,  // 主点 Y (480/2)
  };

  // 默认深度和Z轴厚度（mm）
  const DEFAULT_DEPTH_Z = 810.0;  // 默认深度值（与 MOCK_SUPPORT_Z + z_offset 大致对应）
  const DEFAULT_Z_THICKNESS = 20.0; // Z轴方向的厚度

  // ============================================================================
  // 工具函数
  // ============================================================================

  function el(id) {
    return document.getElementById(id);
  }

  function csrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
  }

  function showStatus(message, type = 'info') {
    const statusEl = el('rack-location-ui-status');
    if (statusEl) {
      statusEl.textContent = message;
      statusEl.className = type === 'error' ? 'error' : type === 'success' ? 'success' : 'muted';
    }
  }

  function getCurrentLayerNo() {
    return Number(el('layer-no')?.value) || 1;
  }

  // ============================================================================
  // Canvas 初始化
  // ============================================================================

  function initCanvas() {
    state.image = el('rack-location-depth-image');
    state.canvas = el('rack-location-canvas');
    
    if (!state.canvas || !state.image) {
      console.warn('[Canvas ROI] Canvas 或 Image 元素未找到');
      return;
    }

    state.ctx = state.canvas.getContext('2d');

    // 监听图像加载完成事件
    if (state.image.complete && state.image.naturalWidth > 0) {
      onImageLoaded();
    }
    state.image.addEventListener('load', onImageLoaded);

    // 添加鼠标事件监听
    state.canvas.addEventListener('mousedown', onMouseDown);
    state.canvas.addEventListener('mousemove', onMouseMove);
    state.canvas.addEventListener('mouseup', onMouseUp);
    state.canvas.addEventListener('mouseleave', onMouseUp);

    // 添加"重画ROI"按钮事件
    const redrawBtn = el('btn-redraw-roi');
    if (redrawBtn) {
      redrawBtn.addEventListener('click', clearROI);
    }

    console.log('[Canvas ROI] Canvas 初始化完成');
  }

  function onImageLoaded() {
    const imgWidth = state.image.naturalWidth;
    const imgHeight = state.image.naturalHeight;

    if (!imgWidth || !imgHeight) {
      console.warn('[Canvas ROI] 图像尺寸无效');
      return;
    }

    // 设置 Canvas 尺寸与图像一致
    state.canvas.width = imgWidth;
    state.canvas.height = imgHeight;

    // 更新相机内参的主点（如果图像尺寸不是640x480）
    CAMERA_INTRINSICS.cx = imgWidth / 2;
    CAMERA_INTRINSICS.cy = imgHeight / 2;

    // 显示Canvas，隐藏提示框
    state.canvas.style.display = 'block';
    const hint = el('roi-coordinate-hint');
    if (hint) {
      hint.style.display = 'none';
    }

    console.log(`[Canvas ROI] 图像已加载: ${imgWidth}x${imgHeight}`);
    showStatus('图像已加载，拖拽鼠标绘制 ROI 框');

    // 如果表单中已有ROI数据，尝试显示
    tryDrawExistingROI();
  }

  // ============================================================================
  // 鼠标事件处理
  // ============================================================================

  function onMouseDown(e) {
    if (!state.canvas || !state.ctx) {
      console.warn('[Canvas ROI] Canvas 未初始化');
      return;
    }

    const rect = state.canvas.getBoundingClientRect();
    const scaleX = state.canvas.width / rect.width;
    const scaleY = state.canvas.height / rect.height;
    
    state.isDrawing = true;
    state.startX = (e.clientX - rect.left) * scaleX;
    state.startY = (e.clientY - rect.top) * scaleY;
    
    // 清空之前的ROI
    clearCanvas();
    showStatus('正在绘制 ROI...');
  }

  function onMouseMove(e) {
    if (!state.isDrawing) return;

    const rect = state.canvas.getBoundingClientRect();
    const scaleX = state.canvas.width / rect.width;
    const scaleY = state.canvas.height / rect.height;
    
    const currentX = (e.clientX - rect.left) * scaleX;
    const currentY = (e.clientY - rect.top) * scaleY;

    // 清空画布重绘
    clearCanvas();

    // 计算矩形尺寸
    const width = currentX - state.startX;
    const height = currentY - state.startY;

    // 绘制半透明填充
    state.ctx.fillStyle = 'rgba(34, 197, 94, 0.15)';
    state.ctx.fillRect(state.startX, state.startY, width, height);

    // 绘制边框
    state.ctx.strokeStyle = '#22c55e';
    state.ctx.lineWidth = 2;
    state.ctx.strokeRect(state.startX, state.startY, width, height);

    // 显示尺寸提示
    const absWidth = Math.abs(width);
    const absHeight = Math.abs(height);
    drawHint(currentX, currentY, `${Math.round(absWidth)} × ${Math.round(absHeight)} px`);
  }

  function onMouseUp(e) {
    if (!state.isDrawing) return;
    state.isDrawing = false;

    const rect = state.canvas.getBoundingClientRect();
    const scaleX = state.canvas.width / rect.width;
    const scaleY = state.canvas.height / rect.height;
    
    const endX = (e.clientX - rect.left) * scaleX;
    const endY = (e.clientY - rect.top) * scaleY;

    // 计算矩形（确保min < max）
    const x1 = Math.min(state.startX, endX);
    const x2 = Math.max(state.startX, endX);
    const y1 = Math.min(state.startY, endY);
    const y2 = Math.max(state.startY, endY);

    // 检查是否绘制了有效的矩形（至少10x10像素）
    if ((x2 - x1) < 10 || (y2 - y1) < 10) {
      clearCanvas();
      showStatus('ROI 太小，请重新绘制（至少 10×10 像素）', 'error');
      return;
    }

    // 边界检查：确保ROI在Canvas范围内
    if (x1 < 0 || x2 > state.canvas.width || y1 < 0 || y2 > state.canvas.height) {
      clearCanvas();
      showStatus('ROI 超出图像边界，请重新绘制', 'error');
      return;
    }

    // 保存当前ROI
    state.currentROI = { x1, y1, x2, y2 };

    // 重绘ROI（最终样式）
    drawFinalROI(x1, y1, x2, y2);

    // 开始坐标转换
    convertPixelToCoordinates(x1, y1, x2, y2);
  }

  // ============================================================================
  // Canvas 绘制工具
  // ============================================================================

  function clearCanvas() {
    if (!state.ctx || !state.canvas) return;
    state.ctx.clearRect(0, 0, state.canvas.width, state.canvas.height);
  }

  function clearROI() {
    clearCanvas();
    state.currentROI = null;
    
    // 清空表单
    ['camera-roi-x-min', 'camera-roi-x-max', 'camera-roi-y-min', 
     'camera-roi-y-max', 'camera-roi-z-min', 'camera-roi-z-max',
     'roi-x-min', 'roi-x-max', 'roi-y-min', 
     'roi-y-max', 'roi-z-min', 'roi-z-max'].forEach(id => {
      const element = el(id);
      if (element) element.value = '';
    });
    
    showStatus('ROI 已清除，可重新绘制');
  }

  function drawFinalROI(x1, y1, x2, y2) {
    clearCanvas();

    const width = x2 - x1;
    const height = y2 - y1;

    // 绘制填充
    state.ctx.fillStyle = 'rgba(34, 197, 94, 0.2)';
    state.ctx.fillRect(x1, y1, width, height);

    // 绘制边框
    state.ctx.strokeStyle = '#22c55e';
    state.ctx.lineWidth = 3;
    state.ctx.strokeRect(x1, y1, width, height);

    // 绘制角点标记
    drawCornerMarkers(x1, y1, x2, y2);

    // 绘制中心点
    const cx = (x1 + x2) / 2;
    const cy = (y1 + y2) / 2;
    state.ctx.fillStyle = '#22c55e';
    state.ctx.beginPath();
    state.ctx.arc(cx, cy, 4, 0, 2 * Math.PI);
    state.ctx.fill();
  }

  function drawCornerMarkers(x1, y1, x2, y2) {
    const markerSize = 12;
    state.ctx.strokeStyle = '#22c55e';
    state.ctx.lineWidth = 3;

    const corners = [
      [x1, y1], [x2, y1], [x1, y2], [x2, y2]
    ];

    corners.forEach(([x, y]) => {
      state.ctx.beginPath();
      state.ctx.moveTo(x - markerSize, y);
      state.ctx.lineTo(x + markerSize, y);
      state.ctx.moveTo(x, y - markerSize);
      state.ctx.lineTo(x, y + markerSize);
      state.ctx.stroke();
    });
  }

  function drawHint(x, y, text) {
    const padding = 8;
    const fontSize = 12;
    
    state.ctx.font = `600 ${fontSize}px monospace`;
    const metrics = state.ctx.measureText(text);
    const textWidth = metrics.width;
    const textHeight = fontSize;

    // 背景
    state.ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
    state.ctx.fillRect(
      x + 10,
      y - textHeight - padding * 2,
      textWidth + padding * 2,
      textHeight + padding * 2
    );

    // 文字
    state.ctx.fillStyle = '#e2e8f0';
    state.ctx.fillText(text, x + 10 + padding, y - padding - 2);
  }

  // ============================================================================
  // 尝试显示已有ROI
  // ============================================================================

  function tryDrawExistingROI() {
    // 检查表单中是否已有相机ROI数据
    const cameraRoiXMin = el('camera-roi-x-min')?.value;
    const cameraRoiXMax = el('camera-roi-x-max')?.value;
    const cameraRoiYMin = el('camera-roi-y-min')?.value;
    const cameraRoiYMax = el('camera-roi-y-max')?.value;

    if (!cameraRoiXMin || !cameraRoiXMax || !cameraRoiYMin || !cameraRoiYMax) {
      return; // 没有已有数据
    }

    // 将相机坐标（mm）反向转换为像素坐标（简化处理）
    // 注意：这只是一个近似显示，实际反向投影需要深度信息
    showStatus('检测到已有 ROI 数据（显示为参考）', 'info');
  }

  // ============================================================================
  // 坐标转换：像素 → 相机坐标 → 机器人坐标
  // ============================================================================

  async function convertPixelToCoordinates(x1, y1, x2, y2) {
    try {
      showStatus('🔄 正在转换坐标...', 'info');

      // 步骤1: 像素坐标 → 相机坐标系 3D ROI
      const cameraROI = pixelToCameraROI(x1, y1, x2, y2);
      console.log('[Canvas ROI] 相机坐标 ROI:', cameraROI);

      // 填充相机坐标到表单
      fillCameraROI(cameraROI);

      // 步骤2: 相机坐标 → 机器人基坐标系（调用后端API）
      const robotROI = await transformCameraToRobot(cameraROI);
      console.log('[Canvas ROI] 机器人坐标 ROI:', robotROI);

      // 填充机器人坐标到表单
      fillRobotROI(robotROI);

      showStatus('✅ ROI 坐标已自动转换并填充', 'success');

      // 自动触发"相机 → 机器人坐标"按钮的状态更新
      const transformBtn = el('btn-transform-roi');
      if (transformBtn) {
        const statusEl = el('roi-transform-status');
        if (statusEl) {
          statusEl.textContent = '✅ 已通过 Canvas 绘制自动转换';
          statusEl.className = 'success';
        }
      }

    } catch (error) {
      console.error('[Canvas ROI] 坐标转换失败:', error);
      showStatus(`❌ 坐标转换失败: ${error.message}`, 'error');
    }
  }

  /**
   * 像素坐标 → 相机坐标系 3D ROI
   * 
   * 使用简化的针孔相机模型：
   * X_camera = (pixel_x - cx) * Z / fx
   * Y_camera = (pixel_y - cy) * Z / fy
   * Z_camera = depth
   */
  function pixelToCameraROI(x1, y1, x2, y2) {
    const { fx, fy, cx, cy } = CAMERA_INTRINSICS;

    // 计算ROI中心的像素坐标
    const centerX = (x1 + x2) / 2;
    const centerY = (y1 + y2) / 2;

    // 使用默认深度值（实际应用中应从深度图获取）
    const depthZ = DEFAULT_DEPTH_Z;

    // 计算ROI中心的相机坐标（mm）
    const camCenterX = (centerX - cx) * depthZ / fx;
    const camCenterY = (centerY - cy) * depthZ / fy;
    const camCenterZ = depthZ;

    // 计算ROI的宽高（像素）
    const widthPx = Math.abs(x2 - x1);
    const heightPx = Math.abs(y2 - y1);

    // 将像素宽高转换为相机坐标系的物理尺寸（mm）
    const widthMm = widthPx * depthZ / fx;
    const heightMm = heightPx * depthZ / fy;

    console.log(`[Canvas ROI] 像素 ROI: [${x1.toFixed(0)}, ${y1.toFixed(0)}, ${x2.toFixed(0)}, ${y2.toFixed(0)}]`);
    console.log(`[Canvas ROI] 物理尺寸: ${widthMm.toFixed(1)}mm × ${heightMm.toFixed(1)}mm`);

    // 构建相机坐标系的 AABB（轴对齐包围盒）
    return {
      x_min: camCenterX - widthMm / 2,
      x_max: camCenterX + widthMm / 2,
      y_min: camCenterY - heightMm / 2,
      y_max: camCenterY + heightMm / 2,
      z_min: camCenterZ - DEFAULT_Z_THICKNESS / 2,
      z_max: camCenterZ + DEFAULT_Z_THICKNESS / 2,
    };
  }

  /**
   * 调用后端API：相机坐标 → 机器人基坐标
   */
  async function transformCameraToRobot(cameraROI) {
    const layerNo = getCurrentLayerNo();
    const recipeId = window.rackLocationRecipeConfig?.recipeId;
    const apiUrl = window.rackLocationRecipeConfig?.transformRoiUrl || '/coordinates/api/transform-roi/';

    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify({
        layer_no: layerNo,
        camera_roi: cameraROI,
        recipe_id: recipeId,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const result = await response.json();

    if (!result.success) {
      const errorMsg = result.error?.message || result.error?.code || '坐标转换失败';
      throw new Error(errorMsg);
    }

    return result.data.robot_roi;
  }

  // ============================================================================
  // 表单填充
  // ============================================================================

  function fillCameraROI(cameraROI) {
    // 临时移除 readonly 属性以允许填充
    const fields = [
      'camera-roi-x-min', 'camera-roi-x-max', 
      'camera-roi-y-min', 'camera-roi-y-max',
      'camera-roi-z-min', 'camera-roi-z-max'
    ];
    
    fields.forEach(id => {
      const field = el(id);
      if (field) {
        const key = id.replace('camera-roi-', '').replace('-', '_');
        field.removeAttribute('readonly');
        field.value = cameraROI[key].toFixed(1);
        field.setAttribute('readonly', true);
      }
    });
  }

  function fillRobotROI(robotROI) {
    const fields = [
      'roi-x-min', 'roi-x-max',
      'roi-y-min', 'roi-y-max',
      'roi-z-min', 'roi-z-max'
    ];
    
    fields.forEach(id => {
      const field = el(id);
      if (field) {
        const key = id.replace('roi-', '').replace('-', '_');
        field.value = robotROI[key].toFixed(1);
      }
    });
  }

  // ============================================================================
  // 初始化入口
  // ============================================================================

  function init() {
    console.log('[Canvas ROI] 模块加载');
    initCanvas();
  }

  // DOM加载完成后初始化
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // 暴露全局接口（用于调试）
  window.RackLocationCanvasROI = {
    state,
    clearROI,
  };

})();
