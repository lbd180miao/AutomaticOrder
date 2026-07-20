import sys

file_path = "templates/vision/foam_inspector_interactive.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''    coverage_threshold: Number(document.getElementById('foam-min-coverage').value || 0.75),
    score_threshold: Number(document.getElementById('foam-min-score').value || 0.80),
    iou_threshold: Number(document.getElementById('foam-min-iou').value || 0.70),'''
replace = '''    coverage_threshold: Number(document.getElementById('foam-min-coverage').value || 0.75),'''

if target in content:
    content = content.replace(target, replace)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Done html save")
else:
    print("Target not found")
