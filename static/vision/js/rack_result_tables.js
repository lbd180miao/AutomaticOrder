(function () {
  'use strict';
  const fmt = (value, digits = 3) => {
    if (!Number.isFinite(value)) return '—';
    const rounded = value.toFixed(digits);
    return Number(rounded) === 0 ? (0).toFixed(digits) : rounded;
  };
  // Show native camera XYZ in the same axis order and signs as the measurement.
  const xyz = values => Array.isArray(values) ? values.map(v => fmt(v)).join(' / ') : '—';
  function cell(row, text, header = false) {
    const item = document.createElement(header ? 'th' : 'td'); item.textContent = text; row.appendChild(item); return item;
  }
  function camera(body, result, reference, names) {
    body.replaceChildren();
    const validXYZ = values => Array.isArray(values) && values.length === 3 && values.every(Number.isFinite);
    // Compare successful camera measurements from the template and current frame.
    const compatible = result?.coordinateSystem === 'camera' && reference?.coordinateSystem === 'camera'
      && result?.success === true && reference?.success === true
      && result?.unit === 'mm' && reference?.unit === 'mm';
    for (const name of names) {
      const standardPoint = reference?.points?.find(point => point.name === name);
      const currentPoint = result?.points?.find(point => point.name === name);
      const standard = reference?.coordinateSystem === 'camera' && reference?.success && standardPoint?.success ? standardPoint.xyz : null;
      const candidate = result?.registration && !result.success;
      const current = result?.registration && result?.coordinateSystem === 'camera' && ((result?.success && currentPoint?.success) || candidate) ? currentPoint?.xyz : null;
      // Display measured coordinate differences only; PLC compensation retains its backend gates.
      const delta = compatible && validXYZ(standard) && validXYZ(current)
        ? current.map((value, axis) => value - standard[axis]) : null;
      const row = document.createElement('tr'); cell(row, `${`模板区域 ${names.indexOf(name) + 1}`}${candidate ? '（候选）' : ''}`, true);
      [standard, current].forEach(values => cell(row, validXYZ(values) ? xyz(values) : '—'));
      {
        const region = result?.registration?.regions?.find(item => item.name === name);
        cell(row, validXYZ(region?.matched_cloud_center_xyz) ? xyz(region.matched_cloud_center_xyz) : '—');
        cell(row, Number.isFinite(region?.fitness) ? `${fmt(region.fitness * 100, 1)}%` : '—');
      }
      cell(row, validXYZ(delta) ? xyz(delta) : '—');
      body.appendChild(row);
    }
  }
  function robotOffsets(robotBody, result, robot, names) {
    robotBody.replaceChildren();
    names.forEach((name, index) => {
      const row = document.createElement('tr'); cell(row, `模板区域 ${index + 1}`, true);
      for (let axis=0; axis<3; axis++) cell(row, robot?.success && result?.registration?.quality_passed ? fmt(robot.offsets?.[index]?.[axis]) : '—');
      robotBody.appendChild(row);
    });
  }
  function history(data, robot = data.robot_result) {
    const result = data.result;
    const reference = data.reference?.measurement || result?.reference;
    const points = [...(reference?.points || []), ...(result?.points || [])];
    const names = points.some(point => point.name === 'P2') ? ['P1', 'P2'] : ['P1'];
    camera(document.getElementById('dpXyzBody'), result, reference, names);
    robotOffsets(document.getElementById('dpRobotBody'), result, robot, names);
  }
  function render(root, evaluation, reference, names) {
    const $ = id => root.querySelector("#" + id);
    const result = evaluation?.result;
    window.rackResultTables.camera($('dp-point-results'), result, reference, names);
    const quality = result?.registration;
    const robot = evaluation?.robot_result;
    window.rackResultTables.robotOffsets($('dp-robot-results'), result, robot, names);
    $('dp-robot-status').textContent = !quality ? '匹配通过且手眼标定、拍照姿态有效后，显示各模板区域中心在机器人基坐标系下的偏差。'
        : !quality.quality_passed ? '当前定位未通过筛选，不输出机器人坐标系偏差。'
          : robot?.success ? (robot.same_pose_assumed ? '基准模板未保存拍照姿态，当前按相同拍照姿态计算。' : '')
            : robot?.errorMessage || '机器人坐标转换不可用，请检查手眼标定和拍照姿态。';
    const failed = !!evaluation && (result?.success === false || quality?.quality_passed === false
      || evaluation.is_success === false || evaluation.locate_ok === false || robot?.success === false);
    const reasons = [];
    const add = value => { if (typeof value === 'string' && value.trim() && !reasons.includes(value.trim())) reasons.push(value.trim()); };
    if (failed) {
      add(evaluation.error_message);
      add(evaluation.failure_reason);
      add(result?.errorMessage);
      (quality?.failure_reasons || []).forEach(add);
      if (robot?.success === false) add(robot.errorMessage || '机器人坐标转换失败，请检查手眼标定和拍照姿态。');
      const limits = quality?.limits || {};
      const checks = [
        ['模板覆盖率', quality?.fitness, limits.min_fitness, true, 100, '%'],
        ...(!quality?.rmse_warning_only ? [['配准残差', quality?.rmse_mm, limits.max_rmse_mm, false, 1, ' mm']] : []),
        ['中心位移', quality?.shift_mm, limits.max_shift_mm, false, 1, ' mm'],
        ['旋转角度', quality?.rotation_deg, limits.max_rotation_deg, false, 1, '°'],
        ['结构约束比', quality?.constraint_ratio, 0.0001, true, 1, ''],
      ];
      checks.forEach(([label, value, limit, minimum, scale, unit]) => {
        if (Number.isFinite(value) && Number.isFinite(limit) && (minimum ? value < limit : value > limit)) {
          const digits = label === '结构约束比' ? 6 : 3;
          add(`${label}不达标：实际 ${fmt(value * scale, digits)}${unit}，要求${minimum ? '至少' : '最多'} ${fmt(limit * scale, digits)}${unit}。`);
        }
      });
      (quality?.quality_warnings || []).forEach(add);
      (quality?.regions || []).forEach((region, index) => {
        if (region.quality_passed === false) add(`区域补充信息（模板区域 ${index + 1}）：${(region.failure_reasons || []).join('；')}；覆盖率 ${fmt(region.fitness * 100, 1)}%，残差 ${fmt(region.rmse_mm)} mm。`);
      });
      const code = evaluation.error_code || result?.errorCode || robot?.errorCode;
      if (code) add(`错误代码：${code}`);
      if (!reasons.length) add('本次检测未通过，检测记录未提供具体原因，请查看设备日志。');
    }
    $('dp-ng-details').hidden = !failed;
    $('dp-ng-reasons').textContent = reasons.map((reason, index) => `${index + 1}. ${reason}`).join('\n');
    $('dp-result-state').textContent = evaluation
      ? result?.registration ? (result.success ? '匹配通过' : '匹配未通过 · 候选结果')
        : result?.success ? '已计算' : `${({'3d':'三维测量失败', input:'输入校验失败', configuration:'配置校验失败', calibration:'标定校验失败'})[result?.stage] || '计算失败'}：${result?.errorMessage || result?.errorCode || '未知原因'}`
      : '待检测';
    if (failed) $('dp-result-state').textContent = 'NG · 检测未通过';
    if (!failed && !quality && !evaluation?.result?.errorMessage) {
      $('dp-result-state').textContent = reference ? '基准已就绪 · 待匹配' : '待建立基准模板';
    }
  }
  window.rackResultTables = {camera, robotOffsets, history, render};
})();
