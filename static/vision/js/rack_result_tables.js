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
  const validXYZ = values => Array.isArray(values) && values.length === 3 && values.every(Number.isFinite);
  const isRivet = (result, reference) => [result, reference].some(item => item?.algorithm_version === 'rivet_relative_v1' || item?.points?.some(p => p.name === 'P3'));
  const labels = {P1: '1 号 · 上横杆', P2: '2 号 · 下横杆', P3: '3 号 · 固定参照'};
  const statuses = {OK_ESTIMATE: '表面估计通过', SPARSE_ESTIMATE: '稀疏点估计通过', NO_DEPTH: '有效深度不足',
    ONE_SIDED_SUPPORT: '中心单侧支撑', INSUFFICIENT_GEOMETRY: '几何支撑不足', UNSTABLE_DEPTH: '深度不稳定'};
  function headers(body, labels) {
    const row = body.closest('table')?.querySelector('thead tr');
    if (row) { row.replaceChildren(); labels.forEach(label => cell(row, label, true)); }
  }
  function relatives(body, result, reference) {
    if (!body) return;
    const rivet = isRivet(result, reference);
    body.closest('[data-relative-section]').hidden = !rivet;
    body.replaceChildren();
    if (!rivet) return;
    (result?.points || reference?.points || []).map(point => point.name).filter(name => name !== 'P3').forEach((name, index) => {
      const row = document.createElement('tr'); cell(row, labels[name], true);
      [reference?.relative_vectors?.[index], result?.success ? result.relative_vectors?.[index] : null,
        result?.success ? result.relative_delta_camera_mm?.[index] : null].forEach(value => cell(row, validXYZ(value) ? xyz(value) : '—'));
      body.appendChild(row);
    });
  }
  function camera(body, result, reference, names) {
    body.replaceChildren();
    const rivet = isRivet(result, reference) || names.includes('P3');
    headers(body, rivet ? ['铆钉', '标准 XYZ（mm）', '当前 XYZ（mm）', '三维取点状态', '检测分（非概率）', '相对 3 号偏差 ΔXYZ（mm）'] : ['模板区域', '标准 XYZ', '当前 XYZ', '匹配后点云中心 XYZ', '匹配分数', '差值 ΔXYZ']);
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
      const relativeDelta = result?.relative_delta_camera_mm?.[names.indexOf(name)];
      const delta = rivet ? (result?.success && validXYZ(relativeDelta) ? relativeDelta : null) : compatible && validXYZ(standard) && validXYZ(current)
        ? current.map((value, axis) => value - standard[axis]) : null;
      const row = document.createElement('tr'); cell(row, `${rivet ? labels[name] : `模板区域 ${names.indexOf(name) + 1}`}${candidate && !currentPoint?.success ? '（未通过）' : ''}`, true);
      [standard, current].forEach(values => cell(row, validXYZ(values) ? xyz(values) : '—'));
      {
        const region = result?.registration?.regions?.find(item => item.name === name);
        const detection = result?.detections?.find(item => item.name === name);
        cell(row, detection ? (detection.error || statuses[detection.measurement?.status] || detection.measurement?.status || '未检测') : validXYZ(region?.matched_cloud_center_xyz) ? xyz(region.matched_cloud_center_xyz) : '—');
        cell(row, detection?.candidates?.length ? fmt(detection.candidates[0].score, 1) : Number.isFinite(region?.fitness) ? `${fmt(region.fitness * 100, 1)}%` : '—');
      }
      cell(row, name === 'P3' && rivet ? '固定参照' : validXYZ(delta) ? xyz(delta) : '—');
      body.appendChild(row);
    }
  }
  function robotOffsets(robotBody, result, robot, names) {
    robotBody.replaceChildren();
    const rivet = isRivet(result) || names.includes('P3');
    headers(robotBody, ['补偿位置', 'ΔX（mm）', 'ΔY（mm）', 'ΔZ（mm）']);
    names.filter(name => name !== 'P3').forEach((name, index) => {
      const row = document.createElement('tr'); cell(row, rivet ? (index === 0 ? '上横杆 A · 1 号相对 3 号' : '下横杆 B · 2 号相对 3 号') : `模板区域 ${index+1}`, true);
      for (let axis=0; axis<3; axis++) cell(row, robot?.success && result?.registration?.quality_passed ? fmt(robot.offsets?.[index]?.[axis]) : '—');
      robotBody.appendChild(row);
    });
  }
  function history(data, robot = data.robot_result) {
    const result = data.result;
    const reference = data.reference?.measurement || result?.reference;
    const points = [...(reference?.points || []), ...(result?.points || [])];
    const names = points.some(point => point.name === 'P3') ? ['P1', 'P2', 'P3'].filter(name => points.some(point => point.name === name)) : points.some(point => point.name === 'P2') ? ['P1', 'P2'] : ['P1'];
    camera(document.getElementById('dpXyzBody'), result, reference, names);
    robotOffsets(document.getElementById('dpRobotBody'), result, robot, names);
    relatives(document.getElementById('dpRelativeBody'), result, reference);
    const help = document.getElementById('dpHistoryMeaning');
    if (help) help.textContent = (data.is_success === false || data.locate_ok === false ? '本次补偿无效，数值仅供诊断。' : '') + (isRivet(result, reference) ? '3 号为固定参照。δ = (Pi − P3) − (Pi0 − P30)，仅旋转到机器人基坐标系；A/B 分别补偿上下横杆，不做整架平移补偿。' : '历史点云模板记录：差值为当前坐标减标准坐标。');
  }
  function render(root, evaluation, reference, names) {
    const $ = id => root.querySelector("#" + id);
    const result = evaluation?.result;
    const rivet = isRivet(result, reference);
    // Keep the active layout: unloading uses P1/P3 only.
    relatives($('dp-relative-results'), result, reference);
    window.rackResultTables.camera($('dp-point-results'), result, reference, names);
    const quality = result?.registration;
    const robot = evaluation?.robot_result;
    window.rackResultTables.robotOffsets($('dp-robot-results'), result, robot, names);
    $('dp-robot-status').textContent = !quality ? '三铆钉检测通过且标定有效后，显示上下横杆相对 3 号的偏差；仅旋转到机器人坐标系。'
        : !quality.quality_passed ? '当前定位未通过筛选，不输出机器人坐标系偏差。'
          : evaluation?.is_success === false || evaluation?.locate_ok === false ? '偏差仅供诊断，本次补偿校验未通过，禁止作为有效补偿发送。'
          : robot?.success ? ((rivet ? 'A 对应上横杆，B 对应下横杆；正值沿机器人基坐标轴正方向。' : '') + (robot.same_pose_assumed ? '基准模板未保存拍照姿态，当前按相同拍照姿态计算。' : ''))
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
      ? result?.registration ? (result.success ? (rivet ? '铆钉检测通过' : '匹配通过') : '检测未通过')
        : result?.success ? '已计算' : `${({'3d':'三维测量失败', input:'输入校验失败', configuration:'配置校验失败', calibration:'标定校验失败'})[result?.stage] || '计算失败'}：${result?.errorMessage || result?.errorCode || '未知原因'}`
      : '待检测';
    if (failed) $('dp-result-state').textContent = 'NG · 检测未通过';
    if (!failed && !quality && !evaluation?.result?.errorMessage) {
      $('dp-result-state').textContent = reference ? '基准已就绪 · 待检测' : '待建立基准模板';
    }
  }
  window.rackResultTables = {camera, robotOffsets, history, render};
})();
