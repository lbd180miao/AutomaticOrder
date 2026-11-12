function foamPercent(ratio) {
  return Number.isFinite(Number(ratio)) && ratio != null
    ? Number(ratio).toLocaleString('zh-CN', {style: 'percent', maximumFractionDigits: 4})
    : '未配置';
}

function foamDecisionSummary(recipe) {
  const thresholds = recipe.threshold_config || {};
  const separated = thresholds.decision_mode === 'separated-v2';
  const alignment = recipe.foam_summary?.alignment || {};
  const unit = alignment.unit;
  const rows = [['判定方式', separated ? '独立完整性与偏移' : '覆盖率与偏移']];
  if (!separated) {
    rows.push(['最低覆盖率', foamPercent(thresholds.coverage_threshold ?? thresholds.minCoverage ?? 0.75)]);
  }
  if (separated || thresholds.min_area_ratio != null || thresholds.max_area_ratio != null) {
    rows.push(['面积比', `${foamPercent(thresholds.min_area_ratio)} ～ ${foamPercent(thresholds.max_area_ratio)}`]);
  }
  if (separated || thresholds.max_missing_ratio != null) {
    rows.push(['最大缺损', foamPercent(thresholds.max_missing_ratio)]);
  }
  if (separated || thresholds.max_excess_ratio != null) {
    rows.push(['最大超出', foamPercent(thresholds.max_excess_ratio)]);
  }
  if (thresholds.max_local_missing_ratio != null) {
    rows.push(['单分区最大缺损', foamPercent(thresholds.max_local_missing_ratio)]);
  }
  rows.push(['X / Y 偏移上限', unit
    ? `${alignment[`max_offset_x_${unit}`]} / ${alignment[`max_offset_y_${unit}`]} ${unit}`
    : '参数待检查']);
  return rows;
}
