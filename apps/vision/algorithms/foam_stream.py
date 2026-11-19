"""Reference-guided foam collapse inspection, independent of Django and camera I/O.

References must be taught on upright foam. Anchor boxes contain rigid product /
fixture features, never the foam itself. Each stream/window owns its own state.
No first-frame self-learning: a clip may start with an already collapsed sheet.
"""
from collections import deque
import json
import math
from pathlib import Path
import time

import cv2
import numpy as np

VERSION = 'foam-collapse-stream-v1'
NORMAL, FALLEN, UNKNOWN = 'NORMAL', 'FALLEN', 'UNKNOWN'


def read_image(path):
    image = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f'无法读取标准图：{path}')
    return image


def box_pixels(box, shape):
    if len(box) != 4 or not all(math.isfinite(float(x)) and 0 <= x <= 1 for x in box):
        raise ValueError('ROI 必须是四个 0~1 的比例坐标')
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        raise ValueError('ROI 宽高必须大于零')
    h, w = shape[:2]
    return tuple(round(v * dim) for v, dim in zip(box, (w, h, w, h)))


class TemporalDecision:
    """Consecutive evidence for the current frame; preserve first NG timestamps."""
    def __init__(self, names, confirm_frames=3, confirm_seconds=.3, max_gap=1.):
        if confirm_frames < 2 or confirm_seconds < 0 or max_gap <= 0:
            raise ValueError('无效的多帧确认参数')
        self.names = tuple(names)
        self.confirm_frames, self.confirm_seconds, self.max_gap = confirm_frames, confirm_seconds, max_gap
        self.reset()

    def reset(self):
        self.history = {s: deque(maxlen=self.confirm_frames) for s in self.names}
        self.since = {}
        self.latched = set()
        self.last_time = None
        self.first_ng = {}

    def update(self, timestamp, observations):
        if not math.isfinite(timestamp) or (self.last_time is not None and timestamp <= self.last_time):
            raise ValueError('帧时间戳必须严格递增，跳转或换视频需重置检测会话')
        if self.last_time is not None and timestamp - self.last_time > self.max_gap:
            for history in self.history.values():
                history.clear()
            self.since.clear()
        self.last_time = timestamp
        results = {}
        for name in self.names:
            state = observations.get(name, UNKNOWN)
            history = self.history[name]
            if state == UNKNOWN or (history and history[-1][1] != state):
                history.clear()
                self.since.pop(name, None)
            if state != UNKNOWN:
                self.since.setdefault(name, timestamp)
                history.append((timestamp, state))
            confirmed = (len(history) == self.confirm_frames and
                         timestamp - self.since[name] + 1e-6 >= self.confirm_seconds)
            current = state if confirmed else UNKNOWN
            if current == FALLEN:
                self.latched.add(name)
                self.first_ng.setdefault(name, timestamp)
            results[name] = {'observation': state, 'state': current,
                             'votes': len(history), 'ng_latched': name in self.latched}
        overall = FALLEN if any(v['state'] == FALLEN for v in results.values()) else (
            NORMAL if all(v['state'] == NORMAL for v in results.values()) else UNKNOWN)
        return {'state': overall, 'sides': results, 'first_ng': dict(self.first_ng)}


class FoamStreamInspector:
    """One instance per clip or production window; process() performs no file writes."""
    def __init__(self, profile_path):
        path = Path(profile_path)
        self.config = json.loads(path.read_text(encoding='utf-8'))
        self.width = int(self.config.get('width', 1200))
        if not 320 <= self.width <= 1600:
            raise ValueError('检测宽度须在 320~1600 之间')
        self.orb = cv2.ORB_create(nfeatures=3000, fastThreshold=7, edgeThreshold=12)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.references = []
        names = None
        for view in self.config['views']:
            ref_path = Path(view['image'])
            gray = read_image(ref_path if ref_path.is_absolute() else path.parent / ref_path)
            gray = self.resize(gray)
            mask = np.zeros_like(gray)
            groups = np.zeros_like(gray)
            if len(view['anchors']) < 2:
                raise ValueError('至少示教两个刚性结构定位区域')
            for i, box in enumerate(view['anchors'], 1):
                x1, y1, x2, y2 = box_pixels(box, gray.shape)
                mask[y1:y2, x1:x2] = 255
                groups[y1:y2, x1:x2] = i
            rois = {s: box_pixels(b, gray.shape) for s, b in view['regions'].items()}
            if not rois or any(min(x2-x1, y2-y1) < 20 for x1,y1,x2,y2 in rois.values()):
                raise ValueError('泡棉检测区域过小或未配置')
            for x1, y1, x2, y2 in rois.values():
                mask[y1:y2, x1:x2] = 0
            keypoints, descriptors = self.orb.detectAndCompute(gray, mask)
            if descriptors is None or len(keypoints) < 20:
                raise ValueError('定位区域纹理不足，请选择孔位、边框接头或标记')
            if names is not None and set(rois) != names:
                raise ValueError('不同观察位置的泡棉编号必须一致')
            names = set(rois)
            self.references.append(dict(name=view['name'], gray=gray, mask=mask, groups=groups,
                                        keypoints=keypoints, descriptors=descriptors, rois=rois))
        if not self.references:
            raise ValueError('请先示教正常泡棉与定位区域')
        self.temporal = TemporalDecision(sorted(names), **self.config.get('temporal', {}))
        self.last_frame_id = -1

    def resize(self, image):
        if image is None or image.size == 0 or image.dtype != np.uint8:
            raise ValueError('需要非空的 8 位相机图像')
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.resize(image, (self.width, round(image.shape[0] * self.width / image.shape[1])),
                          interpolation=cv2.INTER_AREA)

    def reset(self):
        self.temporal.reset()
        self.last_frame_id = -1

    def _register(self, gray):
        keypoints, descriptors = self.orb.detectAndCompute(gray, None)
        if descriptors is None or len(descriptors) < 2:
            return None
        best = None
        for ref in self.references:
            pairs = self.matcher.knnMatch(ref['descriptors'], descriptors, k=2)
            matches = [p[0] for p in pairs if len(p) == 2 and p[0].distance < .75*p[1].distance]
            # A destination feature must not vote multiple times.
            unique = {}
            for match in sorted(matches, key=lambda m: m.distance):
                unique.setdefault(match.trainIdx, match)
            matches = list(unique.values())
            if len(matches) < 12:
                continue
            src = np.float32([ref['keypoints'][m.queryIdx].pt for m in matches])
            dst = np.float32([keypoints[m.trainIdx].pt for m in matches])
            matrix, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                                         ransacReprojThreshold=3)
            if matrix is None:
                continue
            good = inliers.ravel().astype(bool)
            count = int(good.sum())
            scale = float(np.hypot(matrix[0, 0], matrix[0, 1]))
            angle = math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))
            points = src[good]
            groups = {int(ref['groups'][round(y), round(x)]) for x, y in points}
            if (count < 12 or count/len(matches) < .35 or not .8 <= scale <= 1.25 or
                    abs(angle) > 10 or len(groups - {0}) < 2 or np.ptp(points, axis=0).max() < .12*self.width):
                continue
            if best is None or count > best['inliers']:
                best = dict(ref=ref, matrix=matrix, inliers=count, scale=scale, angle=angle)
        return best

    def process(self, image, *, timestamp, frame_id):
        started = time.perf_counter()
        if frame_id <= self.last_frame_id:
            raise ValueError('不能重复处理或倒序处理同一帧')
        gray = self.resize(image)
        registration = self._register(gray)
        details = {}
        if registration is not None:
            ref, matrix = registration['ref'], registration['matrix']
            h, w = ref['gray'].shape
            aligned = cv2.warpAffine(gray, matrix, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
            valid = cv2.warpAffine(np.full_like(gray, 255), matrix, (w, h),
                                   flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP) > 0
            anchor_valid = (ref['mask'] > 0) & valid
            # Compensate modest exposure drift using ONLY rigid anchors.
            offset = float(np.median(aligned[anchor_valid].astype(float)-ref['gray'][anchor_valid]))
            for side, (x1, y1, x2, y2) in ref['rois'].items():
                region = aligned[y1:y2, x1:x2].astype(np.float32) - offset
                standard = ref['gray'][y1:y2, x1:x2].astype(np.float32)
                visible = valid[y1:y2, x1:x2]
                details[side] = self._measure(region, standard, visible)
                corners = np.float32([[x1,y1],[x2,y1],[x2,y2],[x1,y2]])
                mapped = cv2.transform(corners[None], matrix)[0]
                details[side]['polygon'] = (mapped / [gray.shape[1], gray.shape[0]]).tolist()
            pose = {k: registration[k] for k in ('inliers', 'scale', 'angle')}
            pose.update(status='REGISTERED', view=ref['name'])
        else:
            pose = {'status': 'INVALID', 'reason': '未找到可靠的产品/料架定位结构'}
        decision = self.temporal.update(float(timestamp), {s: d['observation'] for s, d in details.items()})
        self.last_frame_id = frame_id
        for side, state in decision['sides'].items():
            state.update(details.get(side, {'reason': '定位失败或不在示教观察范围'}))
        decision.update(version=VERSION, frame_id=frame_id, timestamp=timestamp, registration=pose,
                        elapsed_ms=round((time.perf_counter()-started)*1000, 2))
        return decision

    def _measure(self, region, standard, valid):
        top_end = max(1, round(len(region)*.4))
        if valid.mean() < .85 or valid[:top_end].mean() < .9:
            return {'observation': UNKNOWN, 'reason': '泡棉检测区域不完整'}
        delta = region - standard
        threshold = float(self.config.get('gray_difference', 30))
        bright = (delta > threshold) & valid
        changed = (np.abs(delta) > threshold) & valid
        exposed = float(bright.sum()/valid.sum())
        top_exposed = float(bright[:top_end].sum()/valid[:top_end].sum())
        top_changed = float(changed[:top_end].sum()/valid[:top_end].sum())
        upper = float(np.percentile(standard, 95) + threshold)
        foam = ((region > 25) & (region < upper) & valid).astype(np.uint8)
        foam = cv2.morphologyEx(foam, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
        contours, _ = cv2.findContours(foam, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        area = max((cv2.contourArea(c) for c in contours), default=0) / valid.sum()
        # Bright backing + loss of the upright upper area is evidence of collapse.
        # Darkness alone (shadow, dark foam, blackout) must never become NG.
        if exposed >= .08 and top_exposed >= .15 and top_changed >= .25 and area >= .04:
            observation, reason = FALLEN, '上部展开区域丢失，背板露出，泡棉发生倒伏/折叠'
        elif exposed < .04 and area >= .65:
            observation, reason = NORMAL, '展开区域保持，未见倒伏特征'
        else:
            observation, reason = UNKNOWN, '形态变化待确认或泡棉不可见'
        return {'observation': observation, 'reason': reason, 'exposed_ratio': round(exposed,4),
                'top_exposed_ratio': round(top_exposed,4), 'top_changed_ratio': round(top_changed,4),
                'foam_area_ratio': round(float(area),4)}


def annotate(image, result):
    frame = image.copy()
    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    h, w = frame.shape[:2]
    colors = {NORMAL:(80,210,70), FALLEN:(40,40,240), UNKNOWN:(0,190,245)}
    for side, data in result.get('sides', {}).items():
        color = colors[data['state']]
        if 'polygon' in data:
            points = np.int32(np.array(data['polygon'])*[w,h])
            cv2.polylines(frame, [points], True, color, 2)
            x, y = points[0]
            cv2.putText(frame, f"{side}: {data['state']}", (max(5,x), max(60,y-8)),
                        cv2.FONT_HERSHEY_SIMPLEX, .65, color, 2)
    cv2.rectangle(frame,(0,0),(w,38),(20,25,30),-1)
    cv2.putText(frame, f"{result['state']} | {result['timestamp']:.2f}s | {result['elapsed_ms']:.0f}ms",
                (12,26), cv2.FONT_HERSHEY_SIMPLEX, .7, colors[result['state']], 2)
    return frame
