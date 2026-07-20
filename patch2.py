import sys

file_path = "apps/vision/algorithms/image_io.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target = '''        for side, data in sides.items():
            side_roi = data.get('roi')
            side_box = data.get('box')
            side_label = side_labels.get(side, side)
            
            # 始终绘制配方定义的ROI区域框（蓝色）
            if side_roi:
                draw_roi(out, tuple(side_roi), color=COLOR_ROI, label=side_label, thickness=2)
            
            # 绘制泡棉实际掩膜（红色半透明覆盖）
            side_mask = data.get('mask')
            if side_mask is not None and side_roi:
                rx1, ry1, rx2, ry2 = side_roi'''

replace = '''        for side, data in sides.items():
            original_roi = data.get('original_roi', data.get('roi'))
            side_roi = data.get('roi') # 此为放大的 search_roi
            side_box = data.get('box')
            side_label = side_labels.get(side, side)
            
            # 始终绘制配方定义的用户画的原始 ROI区域框（蓝色）
            if original_roi:
                draw_roi(out, tuple(original_roi), color=COLOR_ROI, label=side_label, thickness=2)
            
            # 绘制泡棉实际掩膜（红色半透明覆盖），需使用放大的 side_roi
            side_mask = data.get('mask')
            if side_mask is not None and side_roi:
                rx1, ry1, rx2, ry2 = side_roi'''

if target in content:
    content = content.replace(target, replace)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Done image_io")
else:
    print("Target not found")
