import sys

file_path = "templates/vision/foam_inspector_interactive.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''    minCoverage: Number(document.getElementById('foam-min-coverage').value || 0.75),
    coverage_threshold: Number(document.getElementById('foam-min-coverage').value || 0.75),
    minScore: Number(document.getElementById('foam-min-score').value || 0.8),
    score_threshold: Number(document.getElementById('foam-min-score').value || 0.8),
    minIoU: Number(document.getElementById('foam-min-iou').value || 0.70),
    iou_threshold: Number(document.getElementById('foam-min-iou').value || 0.70),'''
replace = '''    minCoverage: Number(document.getElementById('foam-min-coverage').value || 0.75),
    coverage_threshold: Number(document.getElementById('foam-min-coverage').value || 0.75),'''

if target in content:
    content = content.replace(target, replace)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Done html save")
else:
    print("Target not found")
