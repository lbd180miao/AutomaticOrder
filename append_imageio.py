"""append dual-rack scene functions to image_io.py"""

code = r'''

# ---------------- 深度相机：双料架合并场景（单次拍摄）----------------

def generate_depth_scene_both(layer_count=3, width=1280, height=480):
    """生成单次拍摄覆盖左右双料架的宽幅深度图（1280x480）。

    硬件确认：3D 相机一次拍摄即可覆盖两个并列料架，此函数模拟该场景。
    图像左半区为左料架，右半区为右料架，中间留分界线。

    返回 (color_depth_image, rois_dict)。
    rois_dict = {
        'LEFT':  {'pillar': (x1,y1,x2,y2), 'region': (x1,y1,x2,y2)},
        'RIGHT': {'pillar': (x1,y1,x2,y2), 'region': (x1,y1,x2,y2)},
    }
    """
    half = width // 2
    yy, xx = np.mgrid[0:height, 0:width]
    depth = (120 + 0.12 * yy + 0.04 * xx).astype(np.float32)

    rois = {}
    for i, side in enumerate(('LEFT', 'RIGHT')):
        base_x = i * half
        pillar_x = base_x + 80
        pillar = (pillar_x, 60, pillar_x + 55, height - 60)
        depth[pillar[1]:pillar[3], pillar[0]:pillar[2]] -= 60

        region_x1 = pillar_x + 80
        region_x2 = min(base_x + half - 30, region_x1 + 280)
        region = (region_x1, 120, region_x2, height - 120)
        depth[region[1]:region[3], region[0]:region[2]] += 30

        if layer_count > 1:
            lh = (region[3] - region[1]) // layer_count
            for j in range(layer_count):
                y1 = region[1] + j * lh
                y2 = min(region[1] + (j + 1) * lh, region[3])
                depth[y1:y2, region[0]:region[2]] += float(j) * 8

        rois[side] = {'pillar': pillar, 'region': region}

    depth_norm = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    color = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)

    for side, roi_data in rois.items():
        region = roi_data['region']
        if layer_count > 1:
            lh = (region[3] - region[1]) // layer_count
            for i in range(1, layer_count):
                ly = region[1] + i * lh
                for sx in range(region[0], region[2], 8):
                    cv2.line(color, (sx, ly), (min(sx + 4, region[2]), ly),
                             (255, 255, 255), 1)
            for i in range(layer_count):
                ly = region[1] + i * lh + lh // 2
                _put_label(color, f'L{layer_count - i}',
                           (region[2] + 4, ly), COLOR_TEXT, scale=0.38)

    cv2.line(color, (half, 0), (half, height), (80, 80, 80), 2)
    return color, rois


def annotate_depth_both(img, rois, side_data, layer_count=3):
    """在双料架宽幅深度图上绘制左右两侧的定位标注。

    参数：
        img      : generate_depth_scene_both() 返回的图像
        rois     : rois_dict，含 LEFT/RIGHT 的 pillar/region
        side_data: {'LEFT': _analyse_side() 结果, 'RIGHT': ...}
    """
    out = img.copy()
    h = height_of(out)

    for side in ('LEFT', 'RIGHT'):
        data = side_data.get(side, {})
        roi_data = rois.get(side, {})
        pillar = roi_data.get('pillar')
        region = roi_data.get('region')
        if pillar is None or region is None:
            continue

        ox = float(data.get('offset_x', 0))
        oy = float(data.get('offset_y', 0))
        oz = float(data.get('offset_z', 0))
        recipe_matched = data.get('recipe_matched', True)
        confidence     = data.get('confidence')
        layer_heights  = data.get('layer_heights')

        if not recipe_matched:
            rx1, _, rx2, _ = region
            cv2.rectangle(out, (rx1, 0), (rx2, 20), (0, 140, 255), -1)
            _put_label(out, 'WARN:超差', (rx1 + 4, 16), (255, 255, 255), scale=0.38)

        draw_roi(out, pillar, color=COLOR_AXIS, label='立柱')
        side_cn = '左侧' if side == 'LEFT' else '右侧'
        draw_roi(out, region, color=COLOR_ROI, label=side_cn)

        cx = (region[0] + region[2]) // 2
        cy = (region[1] + region[3]) // 2
        end = (int(cx + ox * 8), int(cy + oy * 8))
        cv2.arrowedLine(out, (cx, cy), end, COLOR_TEXT, 2, tipLength=0.3)
        cv2.circle(out, (cx, cy), 4, COLOR_TEXT, -1)

        label_x = region[0] + 4
        top_y   = 28 if recipe_matched else 42
        _put_label(out, f'{side_cn}补偿', (label_x, top_y),
                   COLOR_AXIS, scale=0.55, thickness=2)
        _put_label(out, f'X={ox:+.2f} Y={oy:+.2f} Z={oz:+.2f}mm',
                   (label_x, top_y + 18), COLOR_TEXT, scale=0.42)

        if confidence is not None:
            conf_color = COLOR_OK if confidence >= 0.80 else COLOR_WARN
            _put_label(out, f'conf={confidence:.2%}',
                       (label_x, top_y + 34), conf_color, scale=0.42)

        if layer_heights:
            hs = ' '.join(f'L{i+1}:{v:.1f}' for i, v in enumerate(layer_heights))
            _put_label(out, f'层高: {hs}',
                       (region[0] + 4, h - 14), COLOR_TEXT, scale=0.38)

    return out
'''

with open(r'd:\workspace2\AutomaticOrder\apps\vision\algorithms\image_io.py',
          'a', encoding='utf-8') as f:
    f.write(code)
print('done')
