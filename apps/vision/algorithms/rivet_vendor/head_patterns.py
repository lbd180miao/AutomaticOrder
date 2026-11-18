"""Single-image head appearance matching; assets contain no frame positions.

Small exemplar patches cover dark heads with bright rims. Local background
removal and normalized correlation tolerate exposure changes. Negative patches
reject recurring rail/cloth texture. Scores are similarity, not probability.
"""
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np

ASSETS = Path(__file__).resolve().parent/'assets'/'head_patterns.npz'
THRESHOLD = .65


def feature(gray):
    gray = gray.astype(np.float32)
    return gray-cv2.GaussianBlur(gray, (0,0), 6)


@lru_cache(maxsize=1)
def patterns():
    with np.load(ASSETS, allow_pickle=False) as data:
        positives = data['positive']
        negatives = data['negative']
    templates = []
    for patch in positives:
        for angle in range(-80,81,20):
            for scale in [.9,1.,1.1]:
                templates.append(cv2.warpAffine(patch, cv2.getRotationMatrix2D((11,11),angle,scale),
                                               (23,23), borderMode=cv2.BORDER_REFLECT))
    negatives = negatives.reshape(-1,529).astype(np.float32)
    if len(negatives):
        negatives -= negatives.mean(1,keepdims=True)
        negatives /= np.maximum(np.linalg.norm(negatives,axis=1,keepdims=True),1e-6)
    return templates, negatives


def proposals(gray, threshold=THRESHOLD):
    if min(gray.shape) < 23:
        return []
    templates, _ = patterns()
    plane = feature(gray)
    response = np.zeros((gray.shape[0]-22,gray.shape[1]-22),np.float32)
    for template in templates:
        np.maximum(response, cv2.matchTemplate(plane,template,cv2.TM_CCOEFF_NORMED),out=response)
    variance = cv2.boxFilter(plane*plane,-1,(23,23))-cv2.boxFilter(plane,-1,(23,23))**2
    response[variance[11:-11,11:-11] < 225] = 0
    ys,xs = np.where((response >= threshold) &
                     (response == cv2.dilate(response,np.ones((19,19),np.uint8))))
    return sorted([(float(response[y,x]),int(x+11),int(y+11)) for y,x in zip(ys,xs)],reverse=True)


def detect(gray):
    if not ASSETS.exists():
        raise FileNotFoundError(f'缺少铆钉外观模型：{ASSETS}')
    _, negatives = patterns()
    plane = feature(gray)
    hits = []
    for score,u,v in proposals(gray):
        if any(np.hypot(u-h['u'],v-h['v']) < 18 for h in hits):
            continue
        patch = plane[v-11:v+12,u-11:u+12].reshape(-1).copy()
        patch -= patch.mean()
        patch /= max(float(np.linalg.norm(patch)),1e-6)
        negative_score = float(np.max(negatives@patch)) if len(negatives) else 0.
        if negative_score >= score-.035:
            continue
        yy,xx = np.mgrid[v-9:v+10,u-9:u+10]
        values = gray[v-9:v+10,u-9:u+10]
        core = values[(xx-u)**2+(yy-v)**2 <= 7**2]
        ring = values[(xx-u)**2+(yy-v)**2 >= 9**2]
        contrast = float(core.mean()-np.median(ring))
        bright = float(np.mean(core > np.median(ring)+45))
        hits.append(dict(u=float(u),v=float(v),radius_px=8.,
                         score=float(100*score),ranking_score=float(200+100*score),
                         score_kind='appearance_similarity',appearance_similarity=score,
                         background_similarity=negative_score,contrast=contrast,bright_fraction=bright,
                         center_method='head_appearance',center_rechecked=True,boundary_rms_px=None))
    return hits
