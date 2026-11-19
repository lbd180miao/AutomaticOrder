"""Durable per-result NG audit, independent of the two-day PLC diagnostic log."""
import json
import sqlite3
from pathlib import Path
from django.conf import settings
from django.utils import timezone


def database():
    db = sqlite3.connect(Path(settings.DATA_DIR) / 'foam_ng.sqlite3', timeout=5)
    db.execute('''CREATE TABLE IF NOT EXISTS ng_results (
        event_key TEXT PRIMARY KEY, created TEXT NOT NULL, result TEXT NOT NULL)''')
    return db


def record(event_key, result):
    db = database()
    try:
        with db:
            db.execute('INSERT OR IGNORE INTO ng_results VALUES (?, ?, ?)',
                       (event_key, timezone.now().isoformat(), json.dumps(result, ensure_ascii=False)))
    finally:
        db.close()


def recent(limit=300):
    path = Path(settings.DATA_DIR) / 'foam_ng.sqlite3'
    if not path.is_file():
        return []
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=.1)
    try:
        return db.execute('SELECT created, result FROM ng_results ORDER BY rowid DESC LIMIT ?', (limit,)).fetchall()
    finally:
        db.close()
