import sys

file_path = "apps/vision/algorithms/image_io.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''    # 分数
    score_val = result.get('score', 0)
    _put_label(out, f'score={score_val:.3f}', (12, 72), COLOR_WARN, scale=0.45)'''

replace = ""

if target in content:
    content = content.replace(target, replace)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Done image_io score")
else:
    print("Target not found")
