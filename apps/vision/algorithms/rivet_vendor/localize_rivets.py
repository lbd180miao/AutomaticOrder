"""对已逐像素配准的图像和相机 XYZ 点云进行铆钉定位。"""
import argparse
import json
from pathlib import Path
from tempfile import mkdtemp

import cv2
import numpy as np

from . import center_surface
from . import rivet_test as rt


def read_ply(path, count):
    types = dict(char='i1', uchar='u1', short='i2', ushort='u2', int='i4',
                 uint='u4', float='f4', double='f8', float32='f4', float64='f8',
                 uint8='u1', int8='i1', int16='i2', uint16='u2', int32='i4', uint32='u4')
    formats = {'ascii': '=', 'binary_little_endian': '<', 'binary_big_endian': '>'}
    with path.open('rb') as stream:
        if stream.readline().strip() != b'ply':
            raise ValueError('无效的 PLY 文件')
        fmt = element = unit = None
        fields = []
        for line in stream:
            words = line.decode('ascii').split()
            if not words:
                continue
            if words[0] == 'format':
                fmt = words[1]
            elif words[:2] == ['comment', 'length'] and words[2:4] == ['unit', '=']:
                unit = words[-1].lower()
            elif words[0] == 'element':
                if element is None and words[1] != 'vertex':
                    raise ValueError('PLY 的第一个数据段必须为 vertex')
                element = words[1]
                if element == 'vertex' and int(words[2]) != count:
                    raise ValueError('PLY 顶点数必须等于图像像素数，请导出保留无效点的有序点云')
            elif words[0] == 'property' and element == 'vertex':
                if len(words) != 3 or words[1] not in types:
                    raise ValueError('不支持该 PLY 顶点属性')
                fields.append((words[2], types[words[1]]))
            elif words == ['end_header']:
                break
        else:
            raise ValueError('PLY 文件头不完整')
        dtype = np.dtype(fields)
        if fmt not in formats or not {'x', 'y', 'z'}.issubset(dtype.names or ()):
            raise ValueError('PLY 需要包含 x、y、z 顶点属性')
        if fmt == 'ascii':
            vertices = np.loadtxt(stream, dtype=dtype, max_rows=count, ndmin=1)
        else:
            vertices = np.fromfile(stream, dtype=dtype.newbyteorder(formats[fmt]), count=count)
        if len(vertices) != count:
            raise ValueError('PLY 顶点数据不完整')
        return np.column_stack([vertices[k] for k in 'xyz']), unit


def load_cloud(path, shape, unit):
    h, w = shape
    declared = None
    if path.suffix.lower() == '.npy':
        xyz = np.load(path, allow_pickle=False)
    elif path.suffix.lower() == '.ply':
        xyz, declared = read_ply(path, h*w)
    else:
        raise ValueError('请选择 .ply 或 .npy 点云')
    if xyz.shape not in ((h, w, 3), (h*w, 3)) or xyz.dtype.kind not in 'ifu':
        raise ValueError(f'需要数值 XYZ 数组，形状为 ({h},{w},3) 或 ({h*w},3)')
    scales = {'mm': 1, 'millimeter': 1, 'm': 1000, 'meter': 1000}
    if declared and declared not in scales and unit is None:
        raise ValueError('未知 PLY 单位，请通过 --unit 指定 mm 或 m')
    if declared in scales and unit and scales[declared] != scales[unit]:
        raise ValueError('所选单位与 PLY 声明冲突')
    scale = scales[unit or declared or 'mm']
    return xyz.reshape(h, w, 3).astype(np.float64, copy=False) * scale


def measure_with_fallback(cloud, hit):
    primary = rt.measure(cloud, hit)
    if primary['status'] == 'OK_ESTIMATE' and not primary['center_surrounded']:
        primary['status'] = 'ONE_SIDED_SUPPORT'
        primary['candidate_xyz_mm'] = primary.pop('xyz_mm')
        primary['xyz_mm'] = None
        primary['quality_reasons'].append('筛选后的中心邻域有效点未围住圆心')
    if primary['status'] not in ('NO_DEPTH', 'ONE_SIDED_SUPPORT', 'INSUFFICIENT_GEOMETRY'):
        return primary

    # Allow sparse coverage in the larger disk, retaining the same depth filters.
    expanded = rt.measure(cloud, hit, radius_ratio=1., min_valid_ratio=0.)
    expanded['primary_measurement'] = primary
    if expanded['status'] == 'OK_ESTIMATE':
        if expanded['geometry_condition'] > 40:
            expanded['candidate_xyz_mm'] = expanded['xyz_mm']
            expanded['xyz_mm'] = None
            expanded['status'] = 'INSUFFICIENT_GEOMETRY'
        else:
            expanded['status'] = 'SPARSE_ESTIMATE'
            if not expanded['center_surrounded']:
                expanded['quality_reasons'].append('有效点未围住圆心，坐标依赖外推')
    return expanded


def detect_image(gray, roi=None, min_radius=4, max_radius=13, progress=None):
    """Shared GUI/batch 2D scan. No cloud or frame history is accessed."""
    h, w = gray.shape
    roi = roi or (0, 0, w, h)
    # Limit full-frame distance maps while retaining context around tile edges.
    x, y, width, height = roi
    if x < 0 or y < 0 or width < 12 or height < 12 or x+width > w or y+height > h:
        raise ValueError('ROI 越界或过小')
    if not 2 <= min_radius < max_radius:
        raise ValueError('半径范围必须满足 2 <= 最小半径 < 最大半径')
    rows = []
    counts = dict(seeds=0, bright=0, tile_hits=0)
    if progress:
        progress('二维扫描：搜索暗色头部与亮边外观…')
    appearance = rt.detect_head_region(gray,roi,min_radius,max_radius)
    counts['appearance'] = len(appearance)
    if appearance:
        counts['tile_hits'] = len(appearance)
        return appearance,counts
    tiles = ((height+255)//256) * ((width+255)//256)
    done = 0
    pad = 4 * max_radius
    for top in range(y, y+height, 256):
        for left in range(x, x+width, 256):
            x0, y0 = max(x, left-pad), max(y, top-pad)
            x1, y1 = min(x+width, left+256+pad), min(y+height, top+256+pad)
            hits = rt.detect(gray, (x0, y0, x1-x0, y1-y0), min_radius, max_radius,
                             counts=counts,include_appearance=False)
            for hit in hits:
                u, v = hit['u'], hit['v']
                if left <= u < left+256 and top <= v < top+256:
                    if any(np.hypot(u-r['u'], v-r['v']) < 4 for r in rows):
                        continue
                    rows.append(hit)
            done += 1
            if progress:
                progress(f'二维扫描 {done}/{tiles} 块 · 初始圆 {counts["seeds"]} · 已保留候选 {len(rows)}')
    appearance = [hit for hit in rows if hit['center_method'] == 'head_appearance']
    if appearance:
        rows = appearance
    rows.sort(key=lambda hit: hit['ranking_score'], reverse=True)
    merged = []
    for hit in rows:
        separation = 18 if hit['center_method'] == 'head_appearance' else 4
        if all(np.hypot(hit['u']-other['u'],hit['v']-other['v']) >= separation for other in merged):
            merged.append(hit)
    return merged, counts


def localize(image_path, cloud_path, args, progress=None):
    image = rt.read_image(image_path, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cloud = load_cloud(cloud_path, gray.shape, args.unit)
    roi = args.roi or (0,0,gray.shape[1],gray.shape[0])
    rows,counts = detect_image(gray,roi,args.min_radius,args.max_radius,progress)
    for i, hit in enumerate(rows, 1):
        m = measure_with_fallback(cloud, hit)
        hit.update(id=i, measurement=m, center_surface=center_surface.estimate(cloud, hit))
        p = tuple(round(hit[k]) for k in ('u', 'v'))
        radius = round(hit['radius_px'])
        color = (0, 220, 0) if m['xyz_mm'] else (0, 165, 255)
        if m['status'] == 'SPARSE_ESTIMATE':
            color = (255, 195, 45)
        if 'ellipse_axes_px' in hit:
            cv2.ellipse(image, ((float(hit['u']), float(hit['v'])),
                               tuple(hit['ellipse_axes_px']), hit['ellipse_angle_deg']),
                        color, 1, cv2.LINE_AA)
            cv2.drawMarker(image, p, color, cv2.MARKER_CROSS, 5, 1, cv2.LINE_AA)
        else:
            cv2.circle(image, p, radius, color, 2, cv2.LINE_AA)
        cv2.putText(image, str(i), (p[0]+radius, max(14, p[1])), cv2.FONT_HERSHEY_SIMPLEX,
                    .55, color, 2, cv2.LINE_AA)
        print(i, m['status'], m['xyz_mm'] or '')
        if progress:
            progress(f'三维定位 {i}/{len(rows)} · 当前编号 {i} · 检测分 {hit["score"]:.1f}/100')
    args.output.mkdir(parents=True, exist_ok=True)
    folder = Path(mkdtemp(prefix=image_path.stem+'_', dir=args.output))
    cv2.imencode('.png', image)[1].tofile(folder/'annotated.png')
    report = dict(image=str(image_path.resolve()), cloud=str(cloud_path.resolve()), roi=roi,
                  frame='相机坐标系', unit='mm', score_method='appearance_or_brightness_v2', count=len(rows), detection_counts=counts, rivets=rows)
    (folder/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                 allow_nan=False), encoding='utf-8')
    print(f'检测到 {len(rows)} 个候选，结果保存在 {folder.resolve()}')
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--cloud', type=Path)
    parser.add_argument('--unit', choices=['mm', 'm'], help='无单位声明时默认毫米')
    parser.add_argument('--roi', type=int, nargs=4, metavar=('X', 'Y', 'W', 'H'))
    parser.add_argument('--min-radius', type=int, default=4)
    parser.add_argument('--max-radius', type=int, default=13)
    parser.add_argument('--output', type=Path, default=rt.ROOT/'outputs'/'imported')
    parser.add_argument('--no-show', action='store_true')
    args = parser.parse_args()
    if not args.image or not args.cloud:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        def choose(title, pattern):
            name = filedialog.askopenfilename(title=title, filetypes=[(title, pattern)])
            if not name:
                raise SystemExit()
            return Path(name)
        try:
            args.image = args.image or choose('选择二维图像', '*.png *.jpg *.jpeg *.bmp *.tif *.tiff')
            args.cloud = args.cloud or choose('选择配准的相机点云（无单位声明时默认毫米）', '*.ply *.npy')
        finally:
            root.destroy()
    try:
        folder = localize(args.image, args.cloud, args)
        if not args.no_show:
            import os
            os.startfile(folder/'annotated.png')
    except (ValueError, OSError, cv2.error) as exc:
        parser.exit(1, f'处理失败：{exc}\n')


if __name__ == '__main__':
    main()
