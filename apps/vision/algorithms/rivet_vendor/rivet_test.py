"""Standalone, offline rivet detection. No robot or production project imports."""
from pathlib import Path
import argparse
import csv
import json
import numpy as np
import cv2
from . import head_patterns

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT.parent / '采集数据'
DEFAULT_ROI = (120, 375, 110, 90)


def read_image(path, flags=-1):
    image = cv2.imdecode(np.fromfile(path, np.uint8), flags)
    if image is None:
        raise ValueError(f'无法读取图像：{path}')
    return image


def load_frame(folder):
    folder = Path(folder)
    gray = read_image(folder / 'Image.png', 0)
    depth = read_image(folder / 'Depth.tif')
    # Preserve invalid vertices and their indices: never filter before reshape.
    with (folder / 'PointCloud.ply').open('rb') as stream:
        header = []
        for _ in range(100):
            line = stream.readline().decode('ascii').strip()
            header.append(line)
            if line == 'end_header':
                break
        else:
            raise ValueError('PLY 文件头不完整')
        expected = ['property float x', 'property float y', 'property float z',
                    'property uchar red', 'property uchar green', 'property uchar blue']
        if ('format binary_little_endian 1.0' not in header or
                [s for s in header if s.startswith('property ')] != expected):
            raise ValueError('仅支持当前 RVC 导出的 binary little endian XYZRGB PLY')
        if not any('length unit = millimeter' in s for s in header):
            raise ValueError('PLY 未声明毫米单位，拒绝猜测')
        count = int(next(s.split()[-1] for s in header if s.startswith('element vertex ')))
        if count != gray.size or depth.shape != gray.shape:
            raise ValueError('点数、图像和深度图尺寸不一致，不能直接映射')
        vertices = np.fromfile(stream, dtype=[('xyz', '<f4', (3,)), ('rgb', 'u1', (3,))], count=count)
        if len(vertices) != count:
            raise ValueError('PLY 数据被截断')
    cloud = vertices['xyz'].reshape(*gray.shape, 3).copy()
    rgb = vertices['rgb'].reshape(*gray.shape, 3)
    rgb_error = float(np.mean(np.abs(rgb.astype(float) - gray[..., None])))
    valid = np.isfinite(cloud).all(2) & (cloud[..., 2] > 0) & np.isfinite(depth) & (depth > 0)
    if valid.sum() < 100:
        raise ValueError('有效深度点不足')
    depth_error = float(np.percentile(np.abs(cloud[..., 2][valid] - depth[valid] * 1000), 95))
    if rgb_error > 2 or depth_error > 0.1:
        raise ValueError(f'像素对齐校验失败：颜色差={rgb_error:.3f}，深度差={depth_error:.3f} mm')
    return gray, cloud, {'color_mae': rgb_error, 'depth_z_p95_mm': depth_error,
                          'unit': 'mm', 'frame': 'PLY原始坐标系（未转换机器人坐标）'}


MIN_CONTRAST = 22
MIN_BRIGHT_FRACTION = .15


def appearance_score(contrast, bright_fraction):
    """Each brightness feature earns up to 50 points at twice its initial gate."""
    return 50 * (np.clip(contrast / (2 * MIN_CONTRAST), 0, 1)
                 + np.clip(bright_fraction / (2 * MIN_BRIGHT_FRACTION), 0, 1))


def elliptical_highlights(patch, min_radius, max_radius):
    """Find small foreshortened heads that persist across intensity levels.

    Never cut a local window out of a large highlight and call it a head.
    Component size and threshold persistence reject rail/strap fragments.
    """
    tracks = []
    for threshold in range(140, 241, 20):
        _, labels, stats, centers = cv2.connectedComponentsWithStats(
            (patch > threshold).astype('uint8'))
        for idx, (left, top, width, height, area) in enumerate(stats[1:], 1):
            if (area < 12 or max(width, height) > 2*max_radius
                    or max(width, height) < 2*min_radius
                    or min(width, height) < 3
                    or min(left, top, patch.shape[1]-left-width,
                           patch.shape[0]-top-height) < 2):
                continue
            contours, _ = cv2.findContours((labels[top:top+height, left:left+width] == idx).astype('uint8'),
                                          cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            contour = max(contours, key=cv2.contourArea)
            if len(contour) < 5:
                continue
            (cu, cv), axes, angle = cv2.fitEllipse(contour)
            minor, major = sorted(axes)
            if (minor < 1.5 or not 1.6 <= major/minor <= 6
                    or not 2*min_radius <= major <= 2*max_radius
                    or area/(np.pi*minor*major/4) < .65):
                continue
            center = np.array([cu+left, cv+top])
            track = next((t for t in tracks if t[-1][0] == threshold-20
                          and np.linalg.norm(t[-1][1]-center) < 1.5
                          and .65 < major/t[-1][2] < 1.2
                          and .55 < minor/t[-1][3] < 1.2), None)
            item = (threshold, center, major, minor, angle)
            if track is None:
                tracks.append([item])
            else:
                track.append(item)
    hits = []
    for track in tracks:
        if len(track) < 4:
            continue
        _, center, major, minor, angle = track[0]
        u, v = center
        reach = int(np.ceil(major))
        x0, x1 = max(0, int(u)-reach), min(patch.shape[1], int(u)+reach+1)
        y0, y1 = max(0, int(v)-reach), min(patch.shape[0], int(v)+reach+1)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        theta = np.deg2rad(angle)
        a = (xx-u)*np.cos(theta)+(yy-v)*np.sin(theta)
        b = -(xx-u)*np.sin(theta)+(yy-v)*np.cos(theta)
        distance = np.sqrt((a/(minor/2))**2+(b/(major/2))**2)
        crop = patch[y0:y1, x0:x1]
        core, ring = crop[distance <= 1], crop[(distance > 1.5) & (distance < 2.5)]
        if len(core) < 10 or len(ring) < 20:
            continue
        background = float(np.median(ring))
        contrast = float(core.mean()-background)
        bright = float(np.mean(core > background+45))
        if contrast < 44 or bright < .6:
            continue
        hits.append(dict(u=float(u), v=float(v), radius_px=float(major/2),
                         sampling_radius_limit_px=float(minor/2),
                         ellipse_axes_px=[float(minor), float(major)], ellipse_angle_deg=float(angle),
                         score=float(appearance_score(contrast, bright)), ranking_score=contrast+40*bright,
                         contrast=contrast, bright_fraction=bright, center_rechecked=True,
                         center_method='stable_ellipse', boundary_rms_px=None,
                         threshold_support=len(track)))
    return hits


def detect_head_region(gray, roi, min_radius=4, max_radius=13):
    x,y,w,h = roi
    x0,y0 = max(0,x-24),max(0,y-24)
    context = gray[y0:min(gray.shape[0],y+h+24),x0:min(gray.shape[1],x+w+24)]
    hits = []
    for hit in head_patterns.detect(context):
        hit['u'] += x0
        hit['v'] += y0
        if (x <= hit['u'] < x+w and y <= hit['v'] < y+h
                and min_radius <= hit['radius_px'] <= max_radius):
            hits.append(hit)
    return hits


def detect(gray, roi, min_radius=4, max_radius=13, *, counts=None, include_appearance=True):
    if not 2 <= min_radius < max_radius:
        raise ValueError('半径范围必须满足 2 <= 最小半径 < 最大半径')
    x, y, w, h = map(int, roi)
    if x < 0 or y < 0 or w < 12 or h < 12 or x+w > gray.shape[1] or y+h > gray.shape[0]:
        raise ValueError('ROI 越界或过小，请重新框选')
    patch = gray[y:y+h, x:x+w]
    circles = cv2.HoughCircles(cv2.GaussianBlur(patch, (3, 3), 0),
                               cv2.HOUGH_GRADIENT, 1, 8, param1=80, param2=10,
                               minRadius=min_radius, maxRadius=max_radius)
    candidates = []
    if counts is not None:
        counts['seeds'] += 0 if circles is None else len(circles[0])
    yy, xx = np.indices(patch.shape)
    for u, v, radius in ([] if circles is None else circles[0]):
        dist = np.hypot(xx-u, yy-v)
        inner = patch[dist < radius * .9]
        outer = patch[(dist > radius * 1.2) & (dist < radius * 1.65)]
        if len(inner) < 15 or len(outer) < 20 or min(u, v, w-u, h-v) < radius:
            continue
        contrast = float(inner.mean() - np.median(outer))
        bright_fraction = float(np.mean(inner > float(np.median(outer)) + 45))
        # Bright compact metal circle, surrounded by darker rack. Not a probability.
        if contrast < MIN_CONTRAST or bright_fraction < MIN_BRIGHT_FRACTION:
            continue
        if counts is not None:
            counts['bright'] += 1
        # Reject bright cloth/straps whose connected component extends well beyond the circle.
        _, labels, stats, _ = cv2.connectedComponentsWithStats((patch > np.median(outer)+45).astype('uint8'))
        ids = [i for i in np.unique(labels[dist < radius*.7]) if i and stats[i,4] >= 4]
        if not ids:
            continue
        if any(max(stats[i,2:4]) > radius*3 for i in ids):
            # Brightness alone cannot validate the center of a connected strap.
            continue
        component = np.isin(labels, ids)
        cy, cx = np.where(component)
        (ref_u, ref_v), ref_radius = cv2.minEnclosingCircle(np.c_[cx,cy].astype('float32'))
        shift = np.hypot(ref_u-u, ref_v-v)
        if not min_radius <= ref_radius <= max_radius or shift > radius*1.2:
            continue
        # Fit the whole external boundary instead of letting the furthest
        # bright pixel alone determine the center of the enclosing circle.
        contours, _ = cv2.findContours(component.astype('uint8'), cv2.RETR_EXTERNAL,
                                      cv2.CHAIN_APPROX_NONE)
        contour = max(contours, key=cv2.contourArea).reshape(-1, 2).astype(float)
        rechecked = shift > radius*.8
        if rechecked:
            # A displaced Hough seed must correspond to one compact, bright component.
            area = len(cx)
            if len(ids) != 1 or area < .35*np.pi*ref_radius**2:
                continue
            if min(ref_u, ref_v, w-1-ref_u, h-1-ref_v) < ref_radius:
                continue
            ref_dist = np.hypot(xx-ref_u, yy-ref_v)
            core = patch[ref_dist < .9*ref_radius]
            ring = patch[(ref_dist > 1.2*ref_radius) & (ref_dist < 1.65*ref_radius)]
            if len(core) < 15 or len(ring) < 20:
                continue
            background = np.median(ring)
            contrast = float(core.mean() - background)
            bright_fraction = float(np.mean(core > background+45))
            if contrast < MIN_CONTRAST or bright_fraction < .30:
                continue
        fit_method = 'enclosing_circle_fallback'
        fit_rms = None
        if len(contour) >= 12:
            origin = contour.mean(0)
            q = contour - origin
            coeff, _, rank, _ = np.linalg.lstsq(
                np.c_[2*q, np.ones(len(q))], (q*q).sum(1), rcond=None)
            center = origin + coeff[:2]
            distances = np.linalg.norm(contour-center, axis=1)
            fitted_r = float(distances.mean())
            rms = float(np.sqrt(np.mean((distances-fitted_r)**2)))
            angles = np.arctan2(contour[:, 1]-center[1], contour[:, 0]-center[0])
            sectors = np.unique(np.floor((angles+np.pi)/(np.pi/4)).astype(int) % 8)
            if (rank == 3 and len(sectors) >= 7 and rms <= .18*fitted_r
                    and min_radius <= fitted_r <= max_radius
                    and np.linalg.norm(center-[ref_u, ref_v]) <= 1.5):
                ref_u, ref_v = center
                ref_radius, fit_rms, fit_method = fitted_r, rms, 'boundary_circle_fit'
        if any(np.hypot(c['u']-ref_u-x,c['v']-ref_v-y) < 4 for c in candidates):
            continue
        candidates.append({'u': float(ref_u+x), 'v': float(ref_v+y), 'radius_px': float(ref_radius),
                           'score': float(appearance_score(contrast, bright_fraction)),
                           'ranking_score': contrast + 40 * bright_fraction,
                           'contrast': contrast, 'bright_fraction': bright_fraction,
                           'center_rechecked': bool(rechecked), 'center_method': fit_method, 'boundary_rms_px': fit_rms})
    for hit in elliptical_highlights(patch, min_radius, max_radius):
        hit['u'] += x
        hit['v'] += y
        if all(np.hypot(hit['u']-other['u'], hit['v']-other['v']) >
               max(hit['radius_px'], other['radius_px']) for other in candidates):
            candidates.append(hit)
    # Search appearance independently of the bright-circle gate. Context may
    # extend outside a tight user ROI, but candidate centers must remain inside.
    appearance_hits = detect_head_region(gray,roi,min_radius,max_radius) if include_appearance else []
    if counts is not None:
        counts['appearance'] = counts.get('appearance',0)+len(appearance_hits)
    if appearance_hits:
        candidates = appearance_hits
    candidates.sort(key=lambda c: c['ranking_score'], reverse=True)
    if counts is not None:
        counts['tile_hits'] += len(candidates)
    return candidates


def measure(cloud, candidate, radius_ratio=.65, *, min_valid_ratio=.25):
    """Mean Z inside an image-space disk; XYZ follows the center camera ray.

    Never compare pixel u,v with physical point-cloud X,Y. The organized
    cloud must already have passed load_frame's registration checks.
    """
    u, v, r = [candidate[k] for k in ('u', 'v', 'radius_px')]
    if (not np.isfinite([u, v, r, radius_ratio]).all() or r <= 0
            or not 0 < radius_ratio <= 1 or not 0 <= u < cloud.shape[1]
            or not 0 <= v < cloud.shape[0]):
        raise ValueError('无效的中心、半径或采样比例')
    limit = candidate.get('sampling_radius_limit_px', r)
    if not np.isfinite(limit) or limit <= 0:
        raise ValueError('无效的采样半径上限')
    ellipse = candidate.get('ellipse_axes_px')
    if ellipse is None:
        r = min(r, limit/radius_ratio)
    x0, x1 = max(0, int(u-r)), min(cloud.shape[1], int(u+r)+2)
    y0, y1 = max(0, int(v-r)), min(cloud.shape[0], int(v+r)+2)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    mask = (xx-u)**2 + (yy-v)**2 <= (radius_ratio*r)**2
    if ellipse is not None:
        axes = np.asarray(ellipse, dtype=float)*radius_ratio/2
        angle = float(candidate['ellipse_angle_deg'])
        if axes.shape != (2,) or not np.isfinite(axes).all() or np.any(axes <= 0) or not np.isfinite(angle):
            raise ValueError('无效的椭圆采样范围')
        theta = np.deg2rad(angle)
        a = (xx-u)*np.cos(theta)+(yy-v)*np.sin(theta)
        b = -(xx-u)*np.sin(theta)+(yy-v)*np.cos(theta)
        mask = (a/axes[0])**2+(b/axes[1])**2 <= 1
    patch = cloud[y0:y1, x0:x1]
    good = mask & np.isfinite(patch).all(2) & (patch[..., 2] > 0)
    points = patch[good].astype(float)
    result = {'xyz_mm': None, 'valid_count': len(points), 'sample_count': int(mask.sum()),
              'valid_ratio': float(good.sum()/max(mask.sum(), 1)), 'status': 'NO_DEPTH',
              'radius_ratio': radius_ratio, 'sampling_radius_px': float(radius_ratio*r),
              'method': '中心邻域有效点 → MAD剔除异常Z → Z算术平均 → 中心射线还原XYZ',
              'quality_reasons': []}
    if ellipse is not None:
        result.update(sampling_shape='ellipse', sampling_semiaxes_px=axes.tolist(),
                      sampling_angle_deg=angle)
    if len(points):
        raw_z = points[:, 2]
        result.update(raw_z_mean_mm=float(raw_z.mean()), raw_z_min_mm=float(raw_z.min()),
                      raw_z_max_mm=float(raw_z.max()), raw_z_median_mm=float(np.median(raw_z)))
    if len(points) < 6 or result['valid_ratio'] < min_valid_ratio:
        if len(points) < 6:
            result['quality_reasons'].append(f'有效点仅{len(points)}个，至少需要6个')
        if result['valid_ratio'] < min_valid_ratio:
            result['quality_reasons'].append(f'有效比例低于{min_valid_ratio:.0%}')
        return result
    z = points[:, 2]
    median = np.median(z)
    mad = float(np.median(np.abs(z-median)))
    keep = np.abs(z-median) <= max(1.0, 3 * 1.4826 * mad)
    points = points[keep]
    pixels = np.c_[xx[good], yy[good]][keep]
    spread = float(np.percentile(points[:, 2], 90)-np.percentile(points[:, 2], 10))
    retained_ratio = float(keep.mean())
    result.update(inlier_count=len(points), depth_spread_mm=spread, depth_mad_mm=mad,
                  retained_ratio=retained_ratio, rejected_count=int((~keep).sum()),
                  z_mean_mm=float(points[:, 2].mean()), z_min_mm=float(points[:, 2].min()),
                  z_max_mm=float(points[:, 2].max()), z_std_mm=float(points[:, 2].std()),
                  z_median_mm=float(np.median(points[:, 2])),
                  outlier_threshold_mm=float(max(1., 3*1.4826*mad)))
    if len(points) < 6:
        result['status'] = 'UNSTABLE_DEPTH'
        return result
    # Locally interpolate X/Z,Y/Z at the subpixel center; do not average X,Y
    # from asymmetrically missing samples (that moves the detected center).
    design = np.c_[pixels[:, 0]-u, pixels[:, 1]-v, np.ones(len(pixels))]
    fit, _, rank, _ = np.linalg.lstsq(design, points[:, :2]/points[:, 2, None], rcond=None)
    hull = cv2.convexHull(design[:, :2].astype(np.float32))
    result['center_surrounded'] = cv2.pointPolygonTest(hull, (0., 0.), False) > 0
    result['geometry_condition'] = float(np.linalg.cond(design)) if rank == 3 else None
    if rank < 3:
        result['status'] = 'INSUFFICIENT_GEOMETRY'
        return result
    z_est = result['z_mean_mm']
    result['xyz_mm'] = [float(fit[2, 0]*z_est), float(fit[2, 1]*z_est), z_est]
    result['status'] = 'OK_ESTIMATE'
    # A majority plane must not hide a substantial second depth layer.
    if spread > 8 or retained_ratio < .7:
        result['candidate_xyz_mm'] = result['xyz_mm']
        result['xyz_mm'] = None
        result['status'] = 'UNSTABLE_DEPTH'
        if spread > 8:
            result['quality_reasons'].append('保留点Z的P90-P10超过8 mm')
        if retained_ratio < .7:
            result['quality_reasons'].append('异常点超过有效点的30%')
    return result


def analyze(folder, roi=DEFAULT_ROI, min_radius=4, max_radius=13):
    gray, cloud, alignment = load_frame(folder)
    candidates = detect(gray, roi, min_radius, max_radius)
    result = {'sample': Path(folder).name, 'source': str(Path(folder).resolve()), 'roi': list(roi),
              'alignment': alignment, 'candidates': candidates, 'detection': None,
              'measurement': None, 'status': 'NOT_FOUND'}
    if candidates:
        result['detection'] = candidates[0]
        ambiguous = len(candidates) > 1 and candidates[1]['ranking_score'] > candidates[0]['ranking_score']*.85
        if ambiguous:
            result['status'] = 'AMBIGUOUS'
        else:
            result['measurement'] = measure(cloud, candidates[0])
            result['status'] = result['measurement']['status']
    return gray, cloud, result


def annotated(gray, result):
    image = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    x, y, w, h = result['roi']
    cv2.rectangle(image, (x,y), (x+w,y+h), (70,180,255), 2)
    for i, candidate in enumerate(result['candidates']):
        u, v, r = (int(round(candidate[k])) for k in ('u', 'v', 'radius_px'))
        color = (70,255,100) if i == 0 else (255,160,40)
        cv2.circle(image, (u,v), r, color, 2)
        cv2.drawMarker(image, (u,v), color, cv2.MARKER_CROSS, 14, 1)
    lines = [f"{result['sample']}  {result['status']}"]
    if result['detection']:
        c = result['detection']
        lines.append(f"Pixel: ({c['u']:.2f}, {c['v']:.2f})  radius={c['radius_px']:.2f}px")
    m = result['measurement']
    if m and m['xyz_mm']:
        lines.append('XYZ estimate (mm): ' + ', '.join(f'{n:.3f}' for n in m['xyz_mm']))
        lines.append(f"Valid: {m['valid_ratio']:.0%}  depth P90-P10: {m['depth_spread_mm']:.3f}mm")
    elif m and m.get('candidate_xyz_mm'):
        lines.append('REJECTED XYZ (mm): ' + ', '.join(f'{n:.3f}' for n in m['candidate_xyz_mm']))
    for i, line in enumerate(lines):
        cv2.putText(image, line, (20, 32+i*30), cv2.FONT_HERSHEY_SIMPLEX, .7, (0,0,0), 4)
        cv2.putText(image, line, (20, 32+i*30), cv2.FONT_HERSHEY_SIMPLEX, .7, (90,255,120), 1)
    return image


def save_result(gray, result, output):
    target = Path(output) / result['sample']
    target.mkdir(parents=True, exist_ok=True)
    (target/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    cv2.imencode('.png', cv2.cvtColor(annotated(gray, result), cv2.COLOR_RGB2BGR))[1].tofile(target/'annotated.png')
    return target


def batch(data, output, roi, min_radius=4, max_radius=13):
    rows = []
    for folder in sorted(Path(data).iterdir()):
        if not folder.is_dir() or not (folder/'Image.png').exists():
            continue
        try:
            gray, _, result = analyze(folder, roi, min_radius, max_radius)
            save_result(gray, result, output)
            d, m = result['detection'] or {}, result['measurement'] or {}
            xyz = m.get('xyz_mm') or [None]*3
            candidate = m.get('candidate_xyz_mm') or [None]*3
            rows.append({'sample': folder.name, 'status': result['status'], 'u': d.get('u'), 'v': d.get('v'),
                         'x_mm': xyz[0], 'y_mm': xyz[1], 'z_mm': xyz[2],
                         'rejected_x_mm':candidate[0], 'rejected_y_mm':candidate[1], 'rejected_z_mm':candidate[2],
                         'raw_z_mean_mm': m.get('raw_z_mean_mm'), 'filtered_z_mean_mm': m.get('z_mean_mm'),
                         'z_min_mm': m.get('z_min_mm'), 'z_max_mm': m.get('z_max_mm'),
                         'valid_count': m.get('valid_count'), 'inlier_count': m.get('inlier_count'),
                         'depth_spread_mm': m.get('depth_spread_mm'),
                         'valid_ratio': m.get('valid_ratio'), 'error': ''})
        except Exception as exc:
            rows.append({'sample': folder.name, 'status': 'ERROR', 'error': str(exc)})
    Path(output).mkdir(parents=True, exist_ok=True)
    with (Path(output)/'summary.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=['sample','status','u','v','x_mm','y_mm','z_mm',
                                                   'rejected_x_mm','rejected_y_mm','rejected_z_mm',
                                                   'raw_z_mean_mm','filtered_z_mean_mm','z_min_mm','z_max_mm',
                                                   'valid_count','inlier_count','depth_spread_mm','valid_ratio','error'])
        writer.writeheader()
        writer.writerows(rows)
    return rows


def gui(data, output, roi):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from PIL import Image, ImageTk

    class App:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title('铆钉识别独立测试 — 传统视觉 / PLY 三维测量')
            self.root.geometry('1320x900')
            self.data, self.roi, self.result = Path(data), tuple(roi), None
            bar = ttk.Frame(self.root, padding=8); bar.pack(fill='x')
            ttk.Button(bar, text='选择数据根目录', command=self.choose).pack(side='left')
            self.sample = ttk.Combobox(bar, width=15, state='readonly'); self.sample.pack(side='left', padx=8)
            self.sample.bind('<<ComboboxSelected>>', lambda e: self.run())
            ttk.Button(bar, text='重新识别', command=self.run).pack(side='left')
            ttk.Button(bar, text='恢复默认 ROI', command=self.reset).pack(side='left', padx=5)
            ttk.Button(bar, text='导出当前结果', command=self.export).pack(side='left')
            ttk.Button(bar, text='批量测试', command=self.all).pack(side='left', padx=5)
            ttk.Label(bar, text='半径 px:').pack(side='left')
            self.rmin, self.rmax = tk.IntVar(value=4), tk.IntVar(value=13)
            ttk.Spinbox(bar, from_=2, to=50, textvariable=self.rmin, width=4).pack(side='left')
            ttk.Spinbox(bar, from_=3, to=80, textvariable=self.rmax, width=4).pack(side='left')
            ttk.Label(self.root, text='在左图拖动鼠标框选搜索区域后自动识别。绿色为首选候选；橙色为其他候选。坐标为 PLY 原始坐标系、毫米。', padding=5).pack(fill='x')
            body = ttk.Frame(self.root); body.pack(fill='both', expand=True)
            self.canvas = tk.Canvas(body, bg='#17202b', width=960, height=720)
            self.canvas.pack(side='left', fill='both', expand=True)
            right = ttk.Frame(body, width=340, padding=8); right.pack(side='right', fill='y')
            self.zoom = ttk.Label(right); self.zoom.pack()
            self.info = tk.Text(right, width=39, height=29, wrap='word'); self.info.pack(fill='both', expand=True)
            self.canvas.bind('<Configure>', lambda e: self.draw())
            self.canvas.bind('<ButtonPress-1>', self.press)
            self.canvas.bind('<B1-Motion>', self.drag)
            self.canvas.bind('<ButtonRelease-1>', self.release)
            self.refresh()

        def refresh(self):
            items = sorted(p.name for p in self.data.iterdir() if p.is_dir() and (p/'Image.png').exists())
            self.sample['values'] = items
            if items:
                self.sample.set(items[0]); self.run()
            else:
                self.result = None; self.canvas.delete('all'); self.zoom.configure(image='')
                self.info.delete('1.0','end'); self.info.insert('end','目录内未找到包含 Image.png 的采集子目录。')

        def choose(self):
            path = filedialog.askdirectory(initialdir=str(self.data))
            if path:
                self.data = Path(path); self.refresh()

        def reset(self):
            self.roi = DEFAULT_ROI; self.run()

        def run(self):
            try:
                lo, hi = self.rmin.get(), self.rmax.get()
                if lo < 2 or hi <= lo:
                    raise ValueError('最大半径必须大于最小半径，最小半径至少为 2')
                self.gray, self.cloud, self.result = analyze(self.data/self.sample.get(), self.roi, lo, hi)
                self.draw(); self.details()
            except Exception as exc:
                self.result = None; self.canvas.delete('all'); self.zoom.configure(image='')
                self.info.delete('1.0','end'); self.info.insert('end',str(exc))
                messagebox.showerror('分析失败', str(exc))

        def draw(self):
            if not self.result: return
            rgb = annotated(self.gray, self.result)
            h,w = self.gray.shape
            self.scale = min(max(1,self.canvas.winfo_width())/w, max(1,self.canvas.winfo_height())/h)
            self.photo = ImageTk.PhotoImage(Image.fromarray(rgb).resize((max(1,int(w*self.scale)),max(1,int(h*self.scale)))))
            self.canvas.delete('all'); self.canvas.create_image(0,0,anchor='nw',image=self.photo)
            x,y,rw,rh = self.roi
            crop = Image.fromarray(rgb[y:y+rh,x:x+rw]); crop.thumbnail((320,280))
            if max(rw,rh) < 160: crop = Image.fromarray(rgb[y:y+rh,x:x+rw]).resize((320,max(1,int(320*rh/rw))))
            self.zoomphoto = ImageTk.PhotoImage(crop); self.zoom.configure(image=self.zoomphoto)

        def details(self):
            r = self.result; d = r['detection']; m = r['measurement']
            status = {'OK_ESTIMATE':'已识别，获得表面坐标估计', 'NOT_FOUND':'未找到可靠圆形亮目标',
                      'AMBIGUOUS':'多个候选接近，请缩小 ROI', 'NO_DEPTH':'目标深度不足，不输出坐标',
                      'UNSTABLE_DEPTH':'深度分散或分层，候选坐标不合格', 'INSUFFICIENT_GEOMETRY':'有效点几何不足'}
            text = f"样本：{r['sample']}\n状态：{status.get(r['status'],r['status'])}\nROI：{self.roi}\n\n"
            if d: text += f"中心像素：({d['u']:.2f}, {d['v']:.2f})\n半径：{d['radius_px']:.2f} px\n二维亮度分：{d['score']:.1f}/100\n\n"
            if m:
                if m['xyz_mm']: text += '三维表面坐标估计 / mm\n'+'\n'.join(f'{a} = {b:.3f}' for a,b in zip('XYZ',m['xyz_mm']))+'\n\n'
                elif m.get('candidate_xyz_mm'): text += '不合格候选坐标 / mm（仅诊断）\n'+'\n'.join(f'{a} = {b:.3f}' for a,b in zip('XYZ',m['candidate_xyz_mm']))+'\n\n'
                text += f"有效深度：{m['valid_count']}/{m['sample_count']} ({m['valid_ratio']:.0%})\n"
                if 'depth_spread_mm' in m: text += f"深度 P90-P10：{m['depth_spread_mm']:.3f} mm\n"
                if 'raw_z_mean_mm' in m: text += f"原始 Z 均值：{m['raw_z_mean_mm']:.3f} mm\n"
                if 'z_mean_mm' in m:
                    text += f"筛选后 Z 均值：{m['z_mean_mm']:.3f} mm\nZ 范围：{m['z_min_mm']:.3f}～{m['z_max_mm']:.3f} mm\n保留：{m['inlier_count']} 点\n"
                text += '\n'.join(m.get('quality_reasons', []))
            text += '\n映射校验：PLY 颜色对齐原图；Z 与深度图×1000 对齐。\n\n算法：霍夫候选 + 亮区域边界圆拟合；中心邻域剔除异常 Z 后求算术平均，再按中心射线还原 XYZ。\n\n注意：像素 u,v 不等于点云 X,Y。这是可见表面位置估计，不是机械中心。深度离散程度不代表测量精度。'
            self.info.delete('1.0','end'); self.info.insert('end',text)

        def press(self,e):
            if self.result: self.start = (e.x,e.y)

        def drag(self,e):
            if not self.result or not hasattr(self,'start'): return
            self.canvas.delete('selection'); self.canvas.create_rectangle(*self.start,e.x,e.y,outline='yellow',width=2,tags='selection')

        def release(self,e):
            if not self.result or not hasattr(self,'start'): return
            h,w = self.gray.shape
            x0,x1 = sorted((self.start[0]/self.scale,e.x/self.scale)); y0,y1 = sorted((self.start[1]/self.scale,e.y/self.scale))
            x0,x1 = max(0,int(x0)),min(w,int(x1)); y0,y1 = max(0,int(y0)),min(h,int(y1))
            del self.start
            if x1-x0 >= 12 and y1-y0 >= 12:
                self.roi = (x0,y0,x1-x0,y1-y0); self.run()

        def export(self):
            if self.result:
                try: messagebox.showinfo('已导出',str(save_result(self.gray,self.result,output)))
                except Exception as exc: messagebox.showerror('导出失败',str(exc))

        def all(self):
            try:
                rows = batch(self.data,output,self.roi,self.rmin.get(),self.rmax.get())
                messagebox.showinfo('批量完成','\n'.join(f"{r['sample']}: {r['status']}" for r in rows)+f'\n\n输出：{output}')
            except Exception as exc: messagebox.showerror('批量失败',str(exc))

    app = App(); app.root.mainloop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--output', type=Path, default=ROOT/'outputs')
    parser.add_argument('--roi', type=int, nargs=4, default=DEFAULT_ROI, metavar=('X','Y','W','H'))
    parser.add_argument('--batch', action='store_true')
    args = parser.parse_args()
    if args.batch:
        print(json.dumps(batch(args.data,args.output,args.roi), ensure_ascii=False,indent=2))
    else:
        gui(args.data,args.output,args.roi)


