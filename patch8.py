import sys

file_path = "apps/vision/algorithms/foam_inspector.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target1 = '''        'offset_distance_px': 0.0,
        'offset_distance_mm': 0.0,
        'score': 0.0,
        'coverage_threshold': coverage_threshold,'''
replace1 = '''        'offset_distance_px': 0.0,
        'offset_distance_mm': 0.0,
        'coverage_threshold': coverage_threshold,'''

target2 = '''                'iou': iou,
                'score': round(coverage_ratio / max(coverage_threshold, 0.01), 3),
            },'''
replace2 = '''                'iou': iou,
            },'''

target3 = '''    scores = [data.get('score', 0.0) for data in sides.values()]'''
replace3 = ''''''

target4 = '''        'is_aligned': bool(not missing and not misaligned),
        'defect_type': defect_type.value if hasattr(defect_type, 'value') else str(defect_type),
        'score': round(float(min(scores)) if scores else 0.0, 3),
        'offset_x_px': round(float(worst_offset_side.get('offset_x_px', 0.0)), 1),'''
replace4 = '''        'is_aligned': bool(not missing and not misaligned),
        'defect_type': defect_type.value if hasattr(defect_type, 'value') else str(defect_type),
        'offset_x_px': round(float(worst_offset_side.get('offset_x_px', 0.0)), 1),'''

target5 = '''            'is_aligned': False,
            'defect_type': FoamDefectType.MISSING,
            'score': 0.0,
            'offset_x_px': 0.0,'''
replace5 = '''            'is_aligned': False,
            'defect_type': FoamDefectType.MISSING,
            'offset_x_px': 0.0,'''

target6 = '''        'is_aligned': True,
        'defect_type': FoamDefectType.NONE,
        'score': 0.96,
        'offset_x_px': offset_x_px,'''
replace6 = '''        'is_aligned': True,
        'defect_type': FoamDefectType.NONE,
        'offset_x_px': offset_x_px,'''

# I'll just use simple regex or string replaces in python
lines = content.split('\n')
new_lines = []
for line in lines:
    if "scores = [" in line and "sides.values()" in line:
        continue
    if "'score':" in line:
        continue
    new_lines.append(line)

with open(file_path, "w", encoding="utf-8") as f:
    f.write('\n'.join(new_lines))
print("Done foam_inspector score completely")
