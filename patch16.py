import sys

file_path = "templates/vision/foam_inspector_interactive.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''  // IoU
  const iou = data.iou;
  const hasStandardMask = standardPixels && standardPixels > 0;

  if (iou !== null && iou !== undefined) {
    const iouPercent = (iou * 100).toFixed(1) + '%';
    const iouWarning = iou < iouThreshold ? ' ⚠️ 低于' + (iouThreshold * 100).toFixed(0) + '%阈值' : '';
      <strong style="color:"></strong>;
  } else {
      <span style="color:#9ca3af;">-</span>;
  }'''

replace = ""

if target in content:
    content = content.replace(target, replace)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Done removing IoU block")
else:
    print("Target not found")
