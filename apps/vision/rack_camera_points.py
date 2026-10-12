"""Camera-only workbench measurements; never robot compensation or PLC output."""
import copy

import cv2
import numpy as np

from .algorithms.rack_dual_point import (
    VERSION, LocalizationError, detect_line, digest, image_roi, locate_2d,
    measurement_digest, require,
)


def teach_image_edges(image, config):
    """Resolve a newly drawn ROI once, then keep its edge identity on later frames."""
    config = copy.deepcopy(config)
    rois = {r['target']: r for r in config['rois']}
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    for name in ('P1', 'P2'):
        first, second = rois.get(name+'_horizontal'), rois.get(name+'_vertical')
        if first is None or second is None:
            continue
        # Physical part names do not define their orientation in the camera image.
        horizontal = first.get('imageDirection',
            'vertical' if first['height'] > 1.5*first['width'] else 'horizontal') == 'horizontal'
        for roi, is_horizontal in ((first, horizontal), (second, not horizontal)):
            if roi.get('imageDirection') and roi.get('edgeSelection') != 'auto':
                continue
            x0, y0, x1, y1 = image_roi(roi, image.shape)
            patch = gray[y0:y1, x0:x1].astype(np.float32)
            patch = patch if is_horizontal else patch.T
            patch = cv2.GaussianBlur(patch, (3, 3), 0)
            gradient = np.gradient(patch, axis=0)
            profile = np.median(gradient, axis=1)
            noise = float(np.median(np.abs(profile-np.median(profile)))) * 1.4826
            peaks = [i for i in range(3, len(profile)-3)
                     if abs(profile[i]) >= abs(profile[i-1])
                     and abs(profile[i]) > abs(profile[i+1])
                     and abs(profile[i]) >= max(1.0, 3*noise)]
            peaks.sort(key=lambda i: abs(profile[i]), reverse=True)
            errors = []
            for peak in peaks[:8]:
                trial = {**roi, 'imageDirection': 'horizontal' if is_horizontal else 'vertical',
                    'edgeMode': 'single', 'edgeSide': 'upper' if is_horizontal else 'left',
                    'edgePolarity': 'dark_to_light' if profile[peak] > 0 else 'light_to_dark',
                    'expectedPosition': float((y0 if is_horizontal else x0)+peak),
                    'expectedSlope': 0, 'searchHalfWidth': 8,
                    'gradientThreshold': max(1.0, min(10.0, abs(float(profile[peak]))*.4)),
                    'edgeSelection': 'taught'}
                try:
                    line = detect_line(image, trial, config['algorithm'], config['lineQuality'])
                except LocalizationError as exc:
                    errors.append(str(exc))
                    continue
                a, b, c = line['line_abc']
                along = (x0+x1-1)/2 if is_horizontal else (y0+y1-1)/2
                trial['expectedPosition'] = float((-a*along-c)/b if is_horizontal else (-b*along-c)/a)
                trial['expectedSlope'] = float(-a/b if is_horizontal else -b/a)
                roi.update(trial)
                break
            else:
                raise LocalizationError('INSUFFICIENT_EDGES', '2d',
                    f"{roi['target']}：框内未找到连续且高于噪声的边缘，请框住一条清晰边缘。"
                    + (errors[0] if errors else ''))
    return config


def camera_pointmap_measurement(image, cloud, config, metadata):
    """Read legacy RVC camera point maps without inventing a hand-eye contract.

    This is a measured XYZ display, not an independently certified 3D result.
    The RVC capture adapter saves the image and camera-frame point map together.
    Check pixel projection and local surface support before interpolating XYZ.
    """
    result = {'success': False, 'compensation_valid': False, 'plc_publish_allowed': False,
              'algorithm_version': VERSION, 'measurement_only': True}
    try:
        result.update(locate_2d(image, config))
        camera = metadata.get('camera', {})
        require(metadata.get('source') == 'rvc_camera', 'UNVERIFIED_MAPPING', 'input',
                '旧数据包须来自 RVC 同次采集的原图与相机点云')
        unit = camera.get('pointcloud_unit')
        require(unit in ('mm', 'm'), 'UNIT_MISMATCH', 'input', '缺少明确点云单位')
        cloud = np.asarray(cloud, float)
        require(cloud.shape == (*image.shape[:2], 3), 'CLOUD_SHAPE', 'input', '原图与组织化点云尺寸不一致')
        cloud = cloud * (1000 if unit == 'm' else 1)
        # Reject flattened/reordered point maps rather than trusting dimensions alone.
        step = max(1, min(image.shape[:2])//90)
        yy, xx = np.mgrid[:image.shape[0]:step, :image.shape[1]:step]
        sampled = cloud[::step, ::step].reshape(-1, 3)
        valid = np.isfinite(sampled).all(1) & (sampled[:, 2] > 0)
        xyz, uv = sampled[valid], np.c_[xx.ravel(), yy.ravel()][valid]
        require(len(xyz) >= 100, 'INSUFFICIENT_DEPTH', '3d', '点云有效点不足')
        design = np.c_[xyz[:, :2]/xyz[:, 2, None], np.ones(len(xyz))]
        fit = np.linalg.lstsq(design[::2], uv[::2], rcond=None)[0]
        error = np.linalg.norm(design[1::2] @ fit-uv[1::2], axis=1)
        projection_error = float(np.percentile(error, 95))
        require(projection_error <= 5, 'UNVERIFIED_MAPPING', 'input',
                f'点云像素投影检查失败（95%误差 {projection_error:.2f}px）')
        points = []
        for name, pixel in zip(('P1', 'P2'), result['pixels']):
            u, v = pixel
            x, y = int(round(u)), int(round(v))
            x0, x1 = max(0, x-3), min(cloud.shape[1], x+4)
            y0, y1 = max(0, y-3), min(cloud.shape[0], y+4)
            patch = cloud[y0:y1, x0:x1]
            py, px = np.mgrid[y0:y1, x0:x1]
            good = np.isfinite(patch).all(2) & (patch[:, :, 2] > 0)
            require(good.sum() >= 12, 'INSUFFICIENT_DEPTH', '3d', f'{name} 交点附近有效深度不足')
            values, offsets = patch[good], np.c_[px[good]-u, py[good]-v]
            require(np.min(np.linalg.norm(offsets, axis=1)) <= 3, 'DEPTH_HOLE', '3d', f'{name} 交点位于深度空洞')
            depth = values[:, 2]
            require(np.percentile(depth, 90)-np.percentile(depth, 10) <= 20,
                    'DEPTH_DISCONTINUITY', '3d', f'{name} 交点附近存在多个深度表面')
            design = np.c_[offsets, np.ones(len(values))]
            # Start from local consensus, not a least-squares fit pulled by mixed surfaces.
            rng = np.random.default_rng(42)
            mask = np.zeros(len(values), bool)
            best_score = (-1, -np.inf)
            for _ in range(300):
                indices = rng.choice(len(values), 3, replace=False)
                if abs(np.linalg.det(design[indices])) < 1:
                    continue
                candidate = np.linalg.solve(design[indices], values[indices])
                errors = np.linalg.norm(design @ candidate-values, axis=1)
                inliers = errors <= 3.0
                score = (int(inliers.sum()), -float(np.minimum(errors, 3.0).sum()))
                if score > best_score:
                    mask, best_score = inliers, score
            for _ in range(4):
                require(mask.sum() >= 12 and np.linalg.matrix_rank(design[mask]) == 3,
                        'INSUFFICIENT_DEPTH', '3d', f'{name} 局部表面支撑不足')
                fit = np.linalg.lstsq(design[mask], values[mask], rcond=None)[0]
                residual = np.linalg.norm(design @ fit-values, axis=1)
                mask = residual <= 3.0
            require(mask.sum() >= max(12, len(values)*.6), 'DEPTH_QUALITY', '3d', f'{name} 局部点云内点不足（{int(mask.sum())}/{len(values)}，至少 {max(12, int(np.ceil(len(values)*.6)))}；距离阈值 3mm）')
            require(np.min(np.linalg.norm(offsets[mask], axis=1)) <= 2,
                    'DEPTH_HOLE', '3d', f'{name} 交点缺少邻近有效内点')
            hull = cv2.convexHull(offsets[mask].astype(np.float32))
            require(cv2.pointPolygonTest(hull, (0., 0.), False) >= 0,
                    'DEPTH_HOLE', '3d', f'{name} 交点不在有效点支撑范围内')
            fit = np.linalg.lstsq(design[mask], values[mask], rcond=None)[0]
            rms = float(np.sqrt(np.mean(np.sum((design[mask] @ fit-values[mask])**2, axis=1))))
            require(rms <= 1.5, 'DEPTH_QUALITY', '3d', f'{name} 局部点云残差 {rms:.2f}mm 过大')
            points.append({'name': name, 'success': True, 'pixel': pixel, 'xyz': fit[2].tolist(),
                           'model_type': 'local_camera_pointmap', 'valid_points': int(mask.sum()),
                           'geometry_residual': rms})
        result.update(success=True, points=points, unit='mm', coordinateSystem='camera',
            frame_id=metadata.get('package_name') or metadata.get('frame_id'),
            config_digest=measurement_digest(config),
            calibration_digest=digest({'source': 'rvc_camera', 'shape': list(image.shape[:2]),
                                       'sensor': camera.get('serial_number', camera.get('sn')),
                                       'method': 'local_camera_pointmap_v1'}),
            projection_error_p95_px=projection_error, independent_3d_validated=False,
            errorCode='', errorMessage='')
    except (LocalizationError, ValueError, KeyError, TypeError, np.linalg.LinAlgError) as exc:
        result.update(success=False, errorCode=getattr(exc, 'code', 'INVALID_INPUT'),
                      errorMessage=str(exc), stage=getattr(exc, 'stage', 'input'))
    return result
