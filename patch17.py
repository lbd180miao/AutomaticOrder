import sys

file_path = "templates/vision/foam_inspector_interactive.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''  const iouThreshold = thresh.iou_threshold ?? thresh.minIoU ?? 0.70;'''
replace = ""

if target in content:
    content = content.replace(target, replace)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Done html loadThresholds")
else:
    print("Target not found")
