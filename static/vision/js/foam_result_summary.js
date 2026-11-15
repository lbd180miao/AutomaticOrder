window.renderFoamSummary = function(root, r, fallbackRecipeName) {
  const byId = id => root.querySelector('#' + id);
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
  const badge = byId(`${prefix}-status-badge`);
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
  const maxOffsetXMm = data.max_offset_x_mm ?? maxOffsetMm;
  const maxOffsetYMm = data.max_offset_y_mm ?? maxOffsetMm;

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
  byId(`${prefix}-coverage-detail`).innerHTML =
    `<strong style="color:${data.decision_mode === 'separated-v2' ? '#6b7280' : (coverage < coverageThreshold ? '#dc2626' : '#059669')}">${coveragePercent}</strong>${pixelInfo}${coverageWarning}`;



  if (data.integrity) {
    const m = data.integrity;
    const el = byId(`${prefix}-coverage-detail`);
    const details = document.createElement('div');
    details.textContent = `面积比 ${(m.area_ratio * 100).toFixed(1)}% · 对齐后缺损 ${(m.missing_ratio * 100).toFixed(1)}% · 超出 ${(m.excess_ratio * 100).toFixed(1)}% · ${data.fragment_count ?? 1} 个连通区域`;
    el.appendChild(details);
  }

  // 位置偏移
  const offsetMmX = Number(data.offset_x_mm || 0);
  const offsetMmY = Number(data.offset_y_mm || 0);
  if (!data.is_present || !data.alignment_metric) {
    byId(`${prefix}-offset-detail`).innerHTML =
      '<strong style="color:#dc2626;">无法确认（泡棉不存在或覆盖不足）</strong>';
  } else if (data.alignment_metric === 'mm' && maxOffsetMm !== null && maxOffsetMm !== undefined) {
    const exceeded = Math.abs(offsetMmX) > maxOffsetXMm || Math.abs(offsetMmY) > maxOffsetYMm;
    const warning = exceeded ? ` ⚠️ 限值 X±${Number(maxOffsetXMm).toFixed(1)} / Y±${Number(maxOffsetYMm).toFixed(1)}mm` : '';
    byId(`${prefix}-offset-detail`).innerHTML =
      `<strong style="color:${exceeded ? '#dc2626' : '#059669'}">X ${offsetMmX >= 0 ? '+' : ''}${offsetMmX.toFixed(2)} mm · Y ${offsetMmY >= 0 ? '+' : ''}${offsetMmY.toFixed(2)} mm</strong>${warning}`;
  } else {
    byId(`${prefix}-offset-detail`).textContent =
      data.alignment_metric === 'mm' ? `X ${offsetMmX.toFixed(2)} mm · Y ${offsetMmY.toFixed(2)} mm` : '暂无毫米测量值';
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

function setMetricCard(cardId, valId, isOk, label, icon) {
  const card = byId(cardId);
  const val  = byId(valId);
  const iconEl = card.querySelector('.metric-icon');
  card.className = 'metric-card ' + (isOk ? 'ok' : 'ng');
  val.textContent = label;
  if (iconEl) iconEl.textContent = icon + (isOk ? '✓' : '✗');
}

function formatDefect(dt) {
  const map = { NONE: '无缺陷', MISSING: '泡棉缺失/漏贴', MISALIGNED: '位置偏移', LIFTED_EDGE: '边缘起翘' };
  return map[dt] || dt;
}

  // 判定横幅
  const banner = byId('verdict-banner');
  if (banner) {
    banner.className = 'verdict-banner ' + (r.is_passed ? 'pass' : 'fail');
    byId('verdict-icon').textContent = r.is_passed ? '✅' : '❌';
    byId('verdict-text').textContent = r.inspection_status === 'INVALID'
      ? '检测无效 · 请检查图像与配置' : (r.is_passed ? '检测合格 · OK' : '检测不合格 · NG');
    let sub = r.is_passed
      ? '泡棉已检测到，贴附状态合格，进入下一循环'
      : '泡棉检测异常，请查看下方详细信息';
    byId('verdict-sub').textContent = sub;
    const sideStates = Object.values(r.sides || r.result_data?.sides || {});
    const coverageOk = sideStates.every(foamCoverageValid);
    const separated = sideStates.some(d => d.decision_mode === 'separated-v2');
    const presentOk = Boolean(r.is_present) && (separated || coverageOk);
    const alignedOk = presentOk && Boolean(r.is_aligned);
    setMetricCard('card-present', 'value-present', presentOk,
      !r.is_present ? '未检出' : separated ? '已检测（完整性另判）' : coverageOk ? '已检测' : '覆盖不足', '●');
    setMetricCard('card-aligned', 'value-aligned', alignedOk,
      !presentOk ? '无法确认' : alignedOk ? '对齐' : '偏移', '↔');
  }


  // 显示详细结果区域
  byId('detailed-result').style.display = 'block';

  // 配方标题
  const recipeTitle = `【POS${r.position_index} 配方 - 第${r.position_index + 1}层泡棉检测】`;
  const title = byId('result-recipe-title');
  if (title) title.textContent = recipeTitle;

  // 渲染左右侧结果
  if (r.sides && (r.sides.left || r.sides.right)) {
    renderSideResult('left', r.sides.left, r);
    renderSideResult('right', r.sides.right, r);
  } else {
    // 兼容旧格式：没有sides字段时隐藏详细区域
    byId('detailed-result').style.display = 'none';
  }

  // 最终判定
  const finalDiv = byId('final-verdict');
  const finalText = byId('final-verdict-text');
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

  // 详细数值（保留原有显示）
  byId('d-pos').textContent   = r.position_index;
  byId('d-recipe').textContent = r.recipe?.name || fallbackRecipeName || '默认配置';

  const overallCoverage = Math.max(0, Math.min(1, Number(r.coverage_ratio) || 0));
  byId('d-cov').textContent   = (overallCoverage * 100).toFixed(1) + '%';
  byId('d-ox').textContent = r.offset_x_mm == null ? '—' : Number(r.offset_x_mm).toFixed(2) + ' mm';
  byId('d-oy').textContent = r.offset_y_mm == null ? '—' : Number(r.offset_y_mm).toFixed(2) + ' mm';
  byId('detail-row').style.display = 'flex';
  if (!r.is_passed && r.defect_type) {
    byId('d-defect').textContent = formatDefect(r.defect_type);
    byId('d-defect-chip').style.display = '';
  } else {
    byId('d-defect-chip').style.display = 'none';
  }

};
