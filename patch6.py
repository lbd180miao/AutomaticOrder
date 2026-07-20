import sys

file_path = "apps/vision/algorithms/foam_inspector.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''    score = round(float(max(0.0, min(1.0, coverage_ratio / max(coverage_threshold, 0.01)))), 3)
    if iou is not None:
        iou = float(iou)
        score = round(float(min(score, iou)), 3)
        if iou < iou_threshold:
            is_aligned = False'''

replace = '''    if iou is not None:
        iou = float(iou)'''

if target in content:
    content = content.replace(target, replace)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Done foam_inspector logic")
else:
    print("Target not found")
