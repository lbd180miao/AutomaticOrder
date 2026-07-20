import sys

file_path = "apps/vision/algorithms/image_io.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''            elif side_roi:
                # 如果ROI内未检测到泡棉，标注缺失警告
                draw_roi(out, tuple(side_roi), color=COLOR_MISSING, label=f'{side_label} 缺失!', thickness=2)'''

replace = '''            elif original_roi:
                # 如果ROI内未检测到泡棉，标注缺失警告
                draw_roi(out, tuple(original_roi), color=COLOR_MISSING, label=f'{side_label} 缺失!', thickness=2)'''

if target in content:
    content = content.replace(target, replace)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Done image_io missing")
else:
    print("Target not found")
