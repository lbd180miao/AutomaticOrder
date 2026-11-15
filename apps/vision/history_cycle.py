"""Publish and expire the two filesystem history archives under a shared lock."""
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import threading
import time
from contextlib import contextmanager
from contextlib import closing

from django.conf import settings

INTERVAL = 2 * 24 * 60 * 60
logger = logging.getLogger(__name__)


@contextmanager
def locked_state():
    path = Path(settings.DATA_DIR) / '.vision-history-cycle.sqlite3'
    with closing(sqlite3.connect(path, timeout=120)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        yield db


def publish(staging, destination):
    with locked_state():
        os.replace(staging, destination)


def clean_if_due(now=None):
    now = time.time() if now is None else now
    with locked_state() as db:
        db.execute('CREATE TABLE IF NOT EXISTS cycle (id INTEGER PRIMARY KEY, started REAL NOT NULL)')
        row = db.execute('SELECT started FROM cycle WHERE id=1').fetchone()
        if row and now < row[0] + INTERVAL:
            return row[0] + INTERVAL - now
        if row:
            for sdk, path in (('2d_SDK', settings.FOAM_HISTORY_PACKAGE_DIR),
                              ('3d_SDK', settings.VISION_HISTORY_PACKAGE_DIR)):
                root = Path(path)
                if root.resolve() != Path(settings.DATA_DIR).resolve() / sdk / 'pic1':
                    raise ValueError(f'无效历史目录：{root}')
                if not root.exists():
                    continue
                for entry in root.iterdir():
                    if entry.is_symlink():
                        entry.unlink()
                    elif entry.is_dir() and (getattr(entry.lstat(), 'st_file_attributes', 0)
                                             & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                        entry.rmdir()
                    elif entry.is_dir():
                        shutil.rmtree(entry)
                    else:
                        entry.unlink()
        db.execute('INSERT OR REPLACE INTO cycle VALUES (1, ?)', (now,))
    return INTERVAL


def start_history_timer():
    def run():
        while True:
            try:
                delay = clean_if_due()
            except Exception:
                logger.exception('视觉历史文件清理失败，稍后重试')
                delay = 60
            time.sleep(min(3600, delay))

    threading.Thread(target=run, name='vision-history-cleanup', daemon=True).start()
