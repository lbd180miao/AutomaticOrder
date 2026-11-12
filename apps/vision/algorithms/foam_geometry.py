"""Product-only rigid registration and non-filling component grouping."""
import math
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np


class ProductRegistrationError(ValueError):
    pass


def uses_foam_mm_alignment(cfg):
    return (
        float(cfg.get('mm_per_pixel_x', 0) or 0) > 0
        and float(cfg.get('mm_per_pixel_y', 0) or 0) > 0
        and float(cfg.get('max_offset_mm', 0) or 0) > 0
    )


def geometry_config(algorithm):
    result = {}
    specifications = {
        'product_registration': {
            'max_shift_px': (120, 1, 2000), 'max_rotation_deg': (3, 0, 15),
            'min_inliers': (12, 6, 1000), 'min_inlier_ratio': (.55, .1, 1),
            'max_residual_px': (4, .1, 30),
        },
        'fragment_merge': {
            'max_gap_px': (12, 1, 200), 'max_color_distance': (25, 0, 100),
            'min_fragment_area_ratio': (.005, .0001, .25),
            'max_total_area_ratio': (1.5, .1, 3), 'max_extent_ratio': (1.35, 1, 3),
            'max_fragments': (6, 2, 12),
        },
    }
    for name, fields in specifications.items():
        raw = algorithm.get(name) or {}
        if not isinstance(raw, dict) or set(raw) - (set(fields) | {'enabled'}):
            raise ValueError(f'Invalid {name} configuration')
        if not isinstance(raw.get('enabled', False), bool):
            raise ValueError(f'{name}.enabled must be boolean')
        cfg = {'enabled': raw.get('enabled', False)}
        for key, (default, low, high) in fields.items():
            value = float(raw.get(key, default))
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'{name}.{key} must be in [{low}, {high}]')
            if key in ('min_inliers', 'max_fragments'):
                if not value.is_integer():
                    raise ValueError(f'{name}.{key} must be an integer')
                value = int(value)
            cfg[key] = value
        result[name] = cfg
    return result


@lru_cache(maxsize=4)
def _reference_gray(path, mtime, size):
    image = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ProductRegistrationError('product_reference_unreadable')
    h, w = image.shape
    scale = min(1, 1600 / max(h, w))
    return cv2.resize(image, (round(w * scale), round(h * scale))), (h, w)


def register_product(image, reference_path, anchors, foam_boxes, cfg, layer_box):
    """Estimate reference->camera rigid motion from at least two body ROIs.

    Foam search corridors are removed from BOTH feature masks. No automatic
    whole-image fallback is allowed: static fixtures must not become anchors.
    """
    if len(anchors) < 2:
        raise ProductRegistrationError('at_least_two_product_anchors_required')
    path = Path(reference_path)
    if not path.is_file():
        raise ProductRegistrationError('product_reference_missing')
    stat = path.stat()
    reference, expected = _reference_gray(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    if image.shape[:2] != expected:
        raise ProductRegistrationError('product_reference_resolution_mismatch')
    h, w = expected
    sh, sw = reference.shape
    sx, sy = sw / w, sh / h
    current = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (sw, sh))
    contrast = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    reference = contrast.apply(reference)
    current = contrast.apply(current)
    # Exclude every possible foam position under the permitted rigid motion.
    margin = math.ceil(cfg['max_shift_px'] + math.hypot(w, h) * math.sin(math.radians(cfg['max_rotation_deg'])))
    excluded = np.zeros((sh, sw), np.uint8)
    for x1, y1, x2, y2 in foam_boxes:
        a, b = max(0, int((x1*w-margin)*sx)), max(0, int((y1*h-margin)*sy))
        c, d = min(sw, math.ceil((x2*w+margin)*sx)), min(sh, math.ceil((y2*h+margin)*sy))
        excluded[b:d, a:c] = 255
    detector = cv2.ORB_create(nfeatures=1800, fastThreshold=7, edgeThreshold=10)
    source_points, target_points, anchor_ids = [], [], []
    for index, box in enumerate(anchors):
        x1, y1, x2, y2 = box
        a, b, c, d = round(x1*sw), round(y1*sh), round(x2*sw), round(y2*sh)
        source_mask = np.zeros((sh, sw), np.uint8)
        source_mask[b:d, a:c] = 255
        source_mask[excluded > 0] = 0
        target_mask = np.zeros_like(source_mask)
        px, py = math.ceil(margin*sx), math.ceil(margin*sy)
        target_mask[max(0,b-py):min(sh,d+py), max(0,a-px):min(sw,c+px)] = 255
        target_mask[excluded > 0] = 0
        ka, da = detector.detectAndCompute(reference, source_mask)
        kb, db = detector.detectAndCompute(current, target_mask)
        if da is None or db is None or len(da) < 3 or len(db) < 3:
            continue
        source_clearance = cv2.distanceTransform(source_mask, cv2.DIST_L2, 5)
        target_clearance = cv2.distanceTransform(target_mask, cv2.DIST_L2, 5)
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        reverse = {pair[0].queryIdx: pair[0].trainIdx for pair in matcher.knnMatch(db, da, k=2)
                   if len(pair) == 2 and pair[0].distance < .75 * pair[1].distance}
        for pair in matcher.knnMatch(da, db, k=2):
            if len(pair) != 2:
                continue
            m, n = pair
            source_key, target_key = ka[m.queryIdx], kb[m.trainIdx]
            ax, ay = np.rint(source_key.pt).astype(int)
            bx, by = np.rint(target_key.pt).astype(int)
            contained = (source_clearance[ay, ax] >= source_key.size/2 + 2
                         and target_clearance[by, bx] >= target_key.size/2 + 2)
            if contained and m.distance < .75*n.distance and reverse.get(m.trainIdx) == m.queryIdx:
                source_points.append(np.asarray(ka[m.queryIdx].pt) / [sx, sy])
                target_points.append(np.asarray(kb[m.trainIdx].pt) / [sx, sy])
                anchor_ids.append(index)
    if len(source_points) < cfg['min_inliers']:
        raise ProductRegistrationError('insufficient_product_features')
    source, target = np.float32(source_points), np.float32(target_points)
    cv2.setRNGSeed(0)
    affine, inliers = cv2.estimateAffinePartial2D(source, target, method=cv2.RANSAC,
        ransacReprojThreshold=cfg['max_residual_px'], maxIters=3000, confidence=.995)
    if affine is None or inliers is None:
        raise ProductRegistrationError('product_fit_failed')
    keep = inliers.ravel().astype(bool)
    count = int(keep.sum())
    supported = {i for i in set(anchor_ids) if np.count_nonzero(keep & (np.asarray(anchor_ids) == i)) >= 3}
    if count < cfg['min_inliers'] or count/len(keep) < cfg['min_inlier_ratio'] or len(supported) < 2:
        raise ProductRegistrationError('product_match_inconsistent')
    # Rigid refit: do not compensate product scale or foam deformation.
    a, b = source[keep].astype(float), target[keep].astype(float)
    ac, bc = a.mean(axis=0), b.mean(axis=0)
    u, _, vt = np.linalg.svd((a-ac).T @ (b-bc))
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        raise ProductRegistrationError('product_reflection_fit')
    matrix = np.column_stack((rotation, bc - rotation @ ac))
    residual = np.linalg.norm(a @ rotation.T + matrix[:, 2] - b, axis=1)
    angle = math.degrees(math.atan2(rotation[1,0], rotation[0,0]))
    center = np.array([w/2, h/2])
    shift = rotation @ center + matrix[:,2] - center
    scale = math.hypot(affine[0,0], affine[1,0])
    spread = np.linalg.norm(np.ptp(a, axis=0))
    if (abs(scale-1) > .015 or abs(angle) > cfg['max_rotation_deg']
            or np.linalg.norm(shift) > cfg['max_shift_px']
            or np.percentile(residual, 90) > cfg['max_residual_px']
            or spread < .05*math.hypot(w,h)):
        raise ProductRegistrationError('product_motion_out_of_bounds')
    x1,y1,x2,y2 = np.minimum(np.asarray(layer_box)*[w,h,w,h], [w-1,h-1,w-1,h-1])
    corners = np.array([[x1,y1],[x2,y1],[x1,y2],[x2,y2]]) @ rotation.T + matrix[:,2]
    if np.any(corners < -.5) or np.any(corners > [w-.5,h-.5]):
        raise ProductRegistrationError('registered_layer_outside_image')
    inverse = cv2.invertAffineTransform(matrix)
    registered = cv2.warpAffine(image, inverse, (w,h), flags=cv2.INTER_LINEAR)
    return registered, {
        'status': 'REGISTERED', 'method': 'product-orb-rigid-v1',
        'reference_to_camera': matrix.tolist(), 'camera_to_reference': inverse.tolist(),
        'shift_x_px': float(shift[0]), 'shift_y_px': float(shift[1]),
        'rotation_deg': angle, 'inliers': count, 'matches': len(keep),
        'supported_anchors': sorted(supported), 'residual_p90_px': float(np.percentile(residual,90)),
    }


def fragment_groups(labels, stats, image, references, cfg, max_offset_px):
    """Build bounded groups of ORIGINAL components; never paint gap pixels.

    Groups are proposed independently for each side; the final assignment must
    reject overlapping label sets. Singles always remain available.
    """
    h,w = labels.shape
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    colors = np.zeros((len(stats), 3), float)
    for channel in range(3):
        colors[:,channel] = np.bincount(labels.ravel(), weights=lab[:,:,channel].ravel(),
                                        minlength=len(stats)) / np.maximum(stats[:,cv2.CC_STAT_AREA],1)
    result = {}
    for side, reference in references.items():
        area = np.count_nonzero(reference)
        x,y,rw,rh = cv2.boundingRect(reference)
        radius = max(1, int(math.ceil(max_offset_px)))
        support = cv2.dilate(reference, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*radius+1,)*2)) > 0
        overlap = np.bincount(labels[support], minlength=len(stats))
        eligible = [i for i in range(1,len(stats))
                    if stats[i,cv2.CC_STAT_AREA] >= area*cfg['min_fragment_area_ratio']
                    and overlap[i] / stats[i,cv2.CC_STAT_AREA] >= .8]
        # Bound work on reflective images; retain singles in the caller.
        eligible = sorted(eligible, key=lambda i: (-stats[i,cv2.CC_STAT_AREA], i))[:24]
        groups = set()
        for seed in eligible:
            members = {seed}
            combined = labels == seed
            for _ in range(cfg['max_fragments']-1):
                distance = cv2.distanceTransform((~combined).astype(np.uint8), cv2.DIST_L2, 5)
                options = []
                for candidate in eligible:
                    if candidate in members or np.linalg.norm(colors[candidate]-colors[seed]) > cfg['max_color_distance']:
                        continue
                    group = sorted(members | {candidate})
                    total = sum(int(stats[i,cv2.CC_STAT_AREA]) for i in group)
                    boxes = stats[group,:4]
                    extent = (boxes[:,:2]+boxes[:,2:4]).max(axis=0)-boxes[:,:2].min(axis=0)
                    if total > area*cfg['max_total_area_ratio'] or np.any(extent > np.array([rw,rh])*cfg['max_extent_ratio']):
                        continue
                    cx,cy,cw,ch = stats[candidate,:4]
                    local = labels[cy:cy+ch,cx:cx+cw] == candidate
                    gap = float(distance[cy:cy+ch,cx:cx+cw][local].min())
                    if gap <= cfg['max_gap_px']:
                        options.append((gap,candidate))
                if not options:
                    break
                _, candidate = min(options)
                members.add(candidate)
                combined |= labels == candidate
                groups.add(tuple(sorted(members)))
            # Intermediate groups are kept too, avoiding forced over-merging.
        result[side] = sorted(groups)
    return result
