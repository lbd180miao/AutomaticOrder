import sys

file_path = "templates/vision/foam_inspector_interactive.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target1 = '''            <label>最大偏移(px)<input id="foam-max-offset-px" type="number" min="0" step="1" value="30"></label>
            <label>最大偏移(mm)<input id="foam-max-offset-mm" type="number" min="0" step="0.1" value="2"></label>
            <label>X毫米/像素<input id="foam-mm-per-pixel-x" type="number" min="0" step="0.0001" value="0"></label>
            <label>Y毫米/像素<input id="foam-mm-per-pixel-y" type="number" min="0" step="0.0001" value="0"></label>'''

replace1 = '''            <label>最大偏移(mm)<input id="foam-max-offset-mm" type="number" min="0" step="0.1" value="2"></label>
            <label>X像素/毫米<input id="foam-pixels-per-mm-x" type="number" min="0" step="0.1" value="0"></label>
            <label>Y像素/毫米<input id="foam-pixels-per-mm-y" type="number" min="0" step="0.1" value="0"></label>'''

target2 = '''  const maxOffsetPx = thresh.maxOffsetX ?? thresh.max_offset_px ?? 30;
  const maxOffsetMm = thresh.maxOffsetMm ?? thresh.max_offset_mm ?? 2.0;

  document.getElementById('foam-min-coverage').value = minCov;
  document.getElementById('foam-min-score').value = minScore;
  document.getElementById('foam-min-iou').value = minIoU;
  document.getElementById('foam-max-offset-px').value = maxOffsetPx;
  document.getElementById('foam-max-offset-mm').value = maxOffsetMm;
  document.getElementById('foam-mm-per-pixel-x').value = thresh.mm_per_pixel_x ?? thresh.mmPerPixelX ?? 0;
  document.getElementById('foam-mm-per-pixel-y').value = thresh.mm_per_pixel_y ?? thresh.mmPerPixelY ?? 0;'''

replace2 = '''  const maxOffsetMm = thresh.maxOffsetMm ?? thresh.max_offset_mm ?? 2.0;

  document.getElementById('foam-min-coverage').value = minCov;
  document.getElementById('foam-min-score').value = minScore;
  document.getElementById('foam-min-iou').value = minIoU;
  document.getElementById('foam-max-offset-mm').value = maxOffsetMm;
  
  let pxPerMmX = thresh.pixels_per_mm_x ?? 0;
  let pxPerMmY = thresh.pixels_per_mm_y ?? 0;
  if (!pxPerMmX && (thresh.mm_per_pixel_x > 0)) pxPerMmX = Number((1 / thresh.mm_per_pixel_x).toFixed(1));
  if (!pxPerMmY && (thresh.mm_per_pixel_y > 0)) pxPerMmY = Number((1 / thresh.mm_per_pixel_y).toFixed(1));

  document.getElementById('foam-pixels-per-mm-x').value = pxPerMmX;
  document.getElementById('foam-pixels-per-mm-y').value = pxPerMmY;'''

target3 = '''  const maxOffsetPx = Number(document.getElementById('foam-max-offset-px').value || 30);
  const thresholdConfig = {
    ...existingThresholds,
    minCoverage: Number(document.getElementById('foam-min-coverage').value || 0.75),
    coverage_threshold: Number(document.getElementById('foam-min-coverage').value || 0.75),
    minScore: Number(document.getElementById('foam-min-score').value || 0.8),
    score_threshold: Number(document.getElementById('foam-min-score').value || 0.8),
    minIoU: Number(document.getElementById('foam-min-iou').value || 0.70),
    iou_threshold: Number(document.getElementById('foam-min-iou').value || 0.70),
    maxOffsetX: maxOffsetPx,
    maxOffsetY: maxOffsetPx,
    max_offset_px: maxOffsetPx,
    maxOffsetMm: Number(document.getElementById('foam-max-offset-mm').value || 2.0),
    max_offset_mm: Number(document.getElementById('foam-max-offset-mm').value || 2.0),
    mmPerPixelX: Number(document.getElementById('foam-mm-per-pixel-x').value || 0),
    mmPerPixelY: Number(document.getElementById('foam-mm-per-pixel-y').value || 0),
    mm_per_pixel_x: Number(document.getElementById('foam-mm-per-pixel-x').value || 0),
    mm_per_pixel_y: Number(document.getElementById('foam-mm-per-pixel-y').value || 0),
  };'''

replace3 = '''  const thresholdConfig = {
    ...existingThresholds,
    minCoverage: Number(document.getElementById('foam-min-coverage').value || 0.75),
    coverage_threshold: Number(document.getElementById('foam-min-coverage').value || 0.75),
    minScore: Number(document.getElementById('foam-min-score').value || 0.8),
    score_threshold: Number(document.getElementById('foam-min-score').value || 0.8),
    minIoU: Number(document.getElementById('foam-min-iou').value || 0.70),
    iou_threshold: Number(document.getElementById('foam-min-iou').value || 0.70),
    maxOffsetMm: Number(document.getElementById('foam-max-offset-mm').value || 2.0),
    max_offset_mm: Number(document.getElementById('foam-max-offset-mm').value || 2.0),
    pixels_per_mm_x: Number(document.getElementById('foam-pixels-per-mm-x').value || 0),
    pixels_per_mm_y: Number(document.getElementById('foam-pixels-per-mm-y').value || 0),
  };'''

target4 = '''        thresholds: { coverage_threshold: 0.3, max_offset_px: 30, require_dark_support: true },'''
replace4 = '''        thresholds: { coverage_threshold: 0.3, max_offset_mm: 2.0, require_dark_support: true },'''

for t, r in [(target1, replace1), (target2, replace2), (target3, replace3), (target4, replace4)]:
    if t in content:
        content = content.replace(t, r)
    else:
        print(f"Target not found: {t[:50]}...")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done")
