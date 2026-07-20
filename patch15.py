import sys

file_path = "templates/vision/foam_inspector_interactive.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target1 = '''  // 综合得分
  const score = data.score || 0;
  document.getElementById(${prefix}-score).innerHTML = 
    <strong style="color:"></strong>;'''
replace1 = ""

target2 = '''  const iouThreshold = fullResult.sides?.[side]?.iou_threshold || 0.70;'''
replace2 = ""

target3 = '''  // IoU
  const iou = data.iou;
  if (iou !== null && iou !== undefined) {
    const iouPercent = (iou * 100).toFixed(1) + '%';
    const iouWarning = iou < iouThreshold ? ' ⚠️ ＜' + (iouThreshold * 100).toFixed(0) + '%阈值' : '';
    document.getElementById(${prefix}-iou-detail).innerHTML = 
      <strong style="color:"></strong>;
  }'''
replace3 = ""

for t, r in [(target1, replace1), (target2, replace2), (target3, replace3)]:
    content = content.replace(t, r)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done js render")
