"""Persistent foam data, original images and result images."""
import json
import tempfile
import time
from pathlib import Path
import cv2
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import model_to_dict


from django.utils import timezone
from .history_cycle import publish


def root():
    path = Path(settings.FOAM_HISTORY_PACKAGE_DIR)
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


def record_directory(result_id, created_at=None):
    result_id = int(result_id)
    if created_at is not None:
        stamp = timezone.localtime(created_at).strftime('%Y-%m-%d_%H-%M-%S_%f')
        folder = root() / f'{stamp}_{result_id}'
        if folder.is_dir():
            return folder
    else:
        folder = next(root().glob(f'*_{result_id}'), None)
        if folder and folder.is_dir():
            return folder
    return Path(settings.BASE_DIR) / '2d_SDK' / 'pic'


def image_path(result_id, kind, created_at=None):
    if kind not in ('original', 'result'):
        raise ValueError('不支持的图片类型')
    return record_directory(result_id, created_at) / f'{int(result_id)}_{kind}.png'


def archive(result, data):
    import numpy as np
    record = model_to_dict(result)
    record['created_at'] = result.created_at
    record['failure_reason'] = result.failure_reason
    stamp = timezone.localtime(result.created_at).strftime('%Y-%m-%d_%H-%M-%S_%f')
    destination = root() / f'{stamp}_{result.pk}'
    with tempfile.TemporaryDirectory(dir=destination.parent.parent) as staging:
        folder = Path(staging)
        saved = False
        for key, kind in [('original_image', 'original'), ('result_image', 'result')]:
            content = data.get(key)
            if not isinstance(content, bytes):
                continue
            image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_UNCHANGED)
            if image is None:
                raise ValueError('检测图片解码失败')
            ok, encoded = cv2.imencode('.png', image)
            if not ok:
                raise OSError('检测图片保存失败')
            (folder / f'{result.pk}_{kind}.png').write_bytes(encoded.tobytes())
            saved = True
        record['images_saved'] = saved
        (folder / f'{result.pk}.json').write_text(
            json.dumps(record, ensure_ascii=False, indent=2, cls=DjangoJSONEncoder), encoding='utf-8')
        publish(folder, destination)


def save_images(result_id):
    if not has_image(result_id, 'original'):
        raise ValueError('本次检测原图不存在')
    return str(image_path(result_id, 'original').parent)


def image_bytes(result_id, kind):
    if images_deleted(result_id):
        return None
    try:
        return image_path(result_id, kind).read_bytes()
    except FileNotFoundError:
        return None


def has_image(result_id, kind):
    return not images_deleted(result_id) and image_path(result_id, kind).is_file()


def images_deleted(result_id):
    record = record_directory(result_id) / f'{int(result_id)}.json'
    try:
        return json.loads(record.read_text(encoding='utf-8')).get('images_deleted', False)
    except FileNotFoundError:
        return False
