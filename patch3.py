import sys

file_path = "apps/vision/algorithms/image_io.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''            elif side_roi:
                # 框ROI但未检测到泡沫，标注缺失等
                draw_roi(out, tuple(side_roi), color=COLOR_MISSING, label=f'{side_label} 缺失!', thickness=2)'''

replace = '''            elif original_roi:
                # 框ROI但未检测到泡沫，标注缺失等
                draw_roi(out, tuple(original_roi), color=COLOR_MISSING, label=f'{side_label} 缺失!', thickness=2)'''

if target in content:
    content = content.replace(target, replace)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Done image_io 2")
else:
    print("Target not found")
