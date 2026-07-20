import sys

file_path = "apps/vision/algorithms/foam_inspector.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''        'alignment_metric': alignment_metric,
        'score': score,
        'coverage_threshold': float(coverage_threshold),'''

replace = '''        'alignment_metric': alignment_metric,
        'coverage_threshold': float(coverage_threshold),'''

if target in content:
    content = content.replace(target, replace)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Done foam_inspector result")
else:
    print("Target not found")
