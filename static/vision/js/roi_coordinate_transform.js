(function () {
  'use strict';

  const AXES = ['x', 'y', 'z'];
  const BOUNDS = ['min', 'max'];
  let timer = null;

  function csrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
  }

  function endpoint() {
    return window.roiCoordinateConfig?.transformRoiUrl
      || window.rackLocationRecipeConfig?.transformRoiUrl;
  }

  function controls(prefix) {
    const fields = {};
    for (const axis of AXES) {
      for (const bound of BOUNDS) {
        const key = `${axis}_${bound}`;
        fields[key] = document.getElementById(`${prefix}camera-roi-${axis}-${bound}`);
      }
    }
    return fields;
  }

  function readCameraRoi(prefix) {
    const fields = controls(prefix);
    const roi = {};
    for (const [key, field] of Object.entries(fields)) {
      if (!field || field.value.trim() === '') return null;
      roi[key] = Number(field.value);
      if (!Number.isFinite(roi[key])) return null;
    }
    return roi;
  }

  function setRobotRoi(prefix, roi) {
    for (const axis of AXES) {
      for (const bound of BOUNDS) {
        const key = `${axis}_${bound}`;
        const field = document.getElementById(`${prefix}roi-${axis}-${bound}`);
        if (field) field.value = Number(roi[key]).toFixed(3);
      }
    }
  }

  function setStatus(prefix, text, isError) {
    const node = document.getElementById(`${prefix}roi-transform-status`);
    if (!node) return;
    node.textContent = text;
    node.style.color = isError ? '#dc2626' : '#059669';
  }

  function layer(prefix) {
    return Number(document.getElementById(`${prefix}layer`)?.value || 1);
  }

  function recipeId(prefix) {
    if (prefix === 'modal-') {
      const value = document.getElementById('modal-id')?.value;
      return value ? Number(value) : null;
    }
    return window.rackLocationRecipeConfig?.recipeId || null;
  }

  async function transform(prefix, quiet) {
    const cameraRoi = readCameraRoi(prefix);
    if (!cameraRoi) {
      if (!quiet) setStatus(prefix, '请完整填写 6 个相机 ROI 边界。', true);
      return;
    }
    const url = endpoint();
    if (!url) {
      setStatus(prefix, '坐标换算接口未配置。', true);
      return;
    }

    setStatus(prefix, '正在读取坐标模块并换算…', false);
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()},
        body: JSON.stringify({
          layer_no: layer(prefix),
          recipe_id: recipeId(prefix),
          camera_roi: cameraRoi,
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.success) {
        throw new Error(payload.error?.message || '坐标换算失败');
      }
      setRobotRoi(prefix, payload.data.robot_roi);
      window.lastRoiTransform = payload.data;
      if (prefix === '') {
        const handEye = document.getElementById('hand-eye-config-input');
        const capturePose = document.getElementById('capture-pose-input');
        if (handEye) handEye.value = JSON.stringify({matrix: payload.data.hand_eye_matrix});
        if (capturePose) capturePose.value = JSON.stringify(payload.data.robot_pose);
      }
      const pose = payload.data.robot_pose;
      setStatus(
        prefix,
        `已转换为机器人基坐标（${payload.data.coordinate_source}；拍照位 X ${pose.x}, Y ${pose.y}, Z ${pose.z}）`,
        false
      );
    } catch (error) {
      setStatus(prefix, error.message, true);
    }
  }

  function bind(prefix, buttonId) {
    const button = document.getElementById(buttonId);
    const fields = Object.values(controls(prefix)).filter(Boolean);
    if (!button && !fields.length) return;
    button?.addEventListener('click', () => transform(prefix, false));
    fields.forEach((field) => field.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => transform(prefix, true), 300);
    }));
  }

  bind('', 'btn-transform-roi');
  bind('modal-', 'btn-modal-transform-roi');
}());
