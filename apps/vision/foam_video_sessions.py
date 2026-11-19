"""Bounded offline AVI/MP4 decoding sessions. This module has no PLC capability."""
import base64
import threading
import time
import uuid
from pathlib import Path

import cv2
from django.conf import settings

from .algorithms.foam_stream import FoamStreamInspector, annotate


def profile_path():
    import os
    configured = Path(getattr(settings, 'FOAM_STREAM_PROFILE',
                             Path(settings.MEDIA_ROOT)/'vision/foam_stream_templates/pic2/profile.json'))
    # A frozen application's writable data directory can differ from its bundle.
    # Explicit site overrides must never silently fall back to another template.
    if configured.is_file() or os.environ.get('FOAM_STREAM_PROFILE'):
        return configured
    bundled = Path(settings.BASE_DIR)/'media/vision/foam_stream_templates/pic2/profile.json'
    return bundled if bundled.is_file() else configured


def encode_preview(frame, result=None):
    frame = cv2.resize(frame, (1000, round(frame.shape[0]*1000/frame.shape[1])))
    if result is not None:
        frame = annotate(frame, result)
    ok, data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        raise RuntimeError('结果画面编码失败')
    return 'data:image/jpeg;base64,' + base64.b64encode(data).decode('ascii')


class VideoSession:
    def __init__(self, path, *, owned=False, owner=''):
        self.path, self.owned, self.owner = Path(path), owned, owner
        self.lock = threading.Lock()
        self.capture = cv2.VideoCapture(str(path))
        try:
            self.fps = self.capture.get(cv2.CAP_PROP_FPS)
            self.total = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))
            if not self.capture.isOpened() or not 0 < self.fps <= 240 or self.total <= 0:
                raise ValueError('无法解码此视频，请使用有效的 AVI / MP4 / MOV / MKV 文件')
            width, height = self.capture.get(3), self.capture.get(4)
            if width*height > 40_000_000 or self.total/self.fps > 3600:
                raise ValueError('调试视频限制为 4000 万像素、60 分钟以内')
            self.detector = FoamStreamInspector(profile_path())
        except Exception:
            self.capture.release()
            raise
        self.index = 0
        self.touched = time.monotonic()
        self.closed = False

    def metadata(self):
        return {'fps':self.fps,'frames':self.total,'duration':self.total/self.fps,
                'filename':self.path.name,'plc_enabled':False}

    def next(self, seek=None):
        with self.lock:
            if self.closed:
                raise ValueError('视频会话已关闭，请重新导入')
            self.touched = time.monotonic()
            if seek is not None:
                if isinstance(seek, bool) or not isinstance(seek, int):
                    raise ValueError('跳转帧号必须为整数')
                target = int(seek)
                if not 0 <= target < self.total:
                    raise ValueError('跳转帧号超出视频范围')
                if not self.capture.set(cv2.CAP_PROP_POS_FRAMES, target):
                    raise ValueError('该视频不支持跳转')
                self.index = target
                self.detector.reset()
            ok, frame = self.capture.read()
            if not ok:
                if self.index < self.total:
                    raise ValueError(f'视频在第 {self.index} 帧解码失败')
                return {'ended':True,'frame_id':self.index}
            result = self.detector.process(frame, timestamp=self.index/self.fps, frame_id=self.index)
            self.index += 1
            return {'ended':False,'result':result,'image':encode_preview(frame,result),
                    'progress':self.index/self.total,'plc_enabled':False}

    def close(self):
        with self.lock:
            self.closed = True
            self.capture.release()
            if self.owned:
                self.path.unlink(missing_ok=True)


_sessions = {}
_lock = threading.Lock()


def create(path, *, owned=False, owner=''):
    with _lock:
        expired = [key for key,s in _sessions.items() if time.monotonic()-s.touched > 900]
        for key in expired:
            _sessions.pop(key).close()
        if len(_sessions) >= 4:
            raise ValueError('同时最多打开 4 个视频，请先关闭其他视频')
        session = VideoSession(path, owned=owned, owner=owner)
        token = uuid.uuid4().hex
        _sessions[token] = session
        return token, session.metadata()


def get(token, owner):
    with _lock:
        session = _sessions.get(token)
        if session is None or session.owner != owner:
            raise ValueError('视频会话不存在或已过期，请重新导入')
        return session


def close(token, owner):
    with _lock:
        session = _sessions.get(token)
        if session is not None and session.owner == owner:
            _sessions.pop(token).close()
