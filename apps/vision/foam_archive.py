"""Data-only foam archives and bounded, temporary display images."""
import json
import threading
import time
from pathlib import Path
import cv2
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import model_to_dict


_image_lock = threading.Lock()
_latest_id = None
_latest_images = {}


def root():
    path = Path(settings.BASE_DIR) / '2d_SDK' / 'pic'
    path.mkdir(parents=True, exist_ok=True)
    return path


def prune(directory, keep=20):
    files = sorted((p for p in directory.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    for index, path in enumerate(files):
        if index >= keep or time.time() - path.stat().st_mtime > 1800:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def save_image(image, prefix, *args, **kwargs):
    # Original pixels remain lossless and full size; display images are bounded.
    extension = kwargs.get('extension', 'bmp').lower().lstrip('.')
    if extension in ('jpg', 'jpeg'):
        height, width = image.shape[:2]
        scale = min(1.0, 1600 / max(height, width))
        if scale < 1:
            image = cv2.resize(image, (round(width * scale), round(height * scale)),
                               interpolation=cv2.INTER_AREA)
        ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    else:
        ok, encoded = cv2.imencode('.bmp', image)
    if not ok:
        raise OSError('无法编码检测图片')
    h, w = image.shape[:2]
    return encoded.tobytes(), w, h


def image_path(result_id, kind):
    if kind not in ('original', 'result'):
        raise ValueError('不支持的图片类型')
    name = f'{result_id}_{kind}.png'
    permanent = root() / name
    return permanent


def archive(result, data):
    global _latest_id, _latest_images
    with _image_lock:
        _latest_id = result.id
        _latest_images = {
            kind: data[key] for key, kind in
            [('original_image', 'original'), ('result_image', 'result')]
            if isinstance(data.get(key), bytes)
        }
    record = model_to_dict(result)
    record['created_at'] = result.created_at
    record['images_saved'] = False
    path = root() / f'{result.id}.json'
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2, cls=DjangoJSONEncoder), encoding='utf-8')


def save_images(result_id):
    content = image_bytes(result_id, 'original')
    if content is None:
        raise ValueError('本次原图缓存已过期，请重新检测后保存图片')
    target = image_path(result_id, 'original')
    if not target.exists():
        # PNG compression is paid only when the operator explicitly saves.
        import numpy as np
        original = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if original is None:
            raise ValueError('原图解码失败')
        ok, encoded = cv2.imencode('.png', original)
        if not ok:
            raise OSError('原图编码失败')
        target.write_bytes(encoded.tobytes())
    record_path = root() / f'{result_id}.json'
    record = json.loads(record_path.read_text(encoding='utf-8'))
    record['images_saved'] = True
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(root())


def image_bytes(result_id, kind):
    path = image_path(result_id, kind)
    if path.is_file():
        return path.read_bytes()
    with _image_lock:
        return _latest_images.get(kind) if _latest_id == result_id else None


def has_image(result_id, kind):
    if image_path(result_id, kind).is_file():
        return True
    with _image_lock:
        return _latest_id == result_id and kind in _latest_images
