"""Durable AGV outbox. Only the transport worker accesses the gateway."""
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import requests
from django.conf import settings

from .client import MesClient

_wake = threading.Event()
_lock = threading.Lock()
_started = False


class RemotePending(Exception):
    """Yield the PLC scan while a durable MES request is in flight."""


def config():
    return json.loads((Path(settings.DATA_DIR) / 'agv_gateway.json').read_text(encoding='utf-8-sig'))


@contextmanager
def database():
    connection = sqlite3.connect(Path(settings.DATA_DIR) / 'mes_outbox.sqlite3', timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, business_key TEXT UNIQUE, action TEXT, payload TEXT,
        state TEXT, result TEXT, error TEXT, created REAL, updated REAL)''')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def rows():
    with database() as db:
        return [dict(row) for row in db.execute('SELECT * FROM tasks ORDER BY created DESC LIMIT 100')]


def health():
    cfg = config()
    started = time.monotonic()
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(cfg['gateway_url'].rstrip('/') + '/api/health',
                               headers={'Authorization': 'Bearer ' + cfg['token']}, timeout=(3, 5))
        response.raise_for_status()
        result = response.json()
    if result.get('role') != 'mes_gateway' or result.get('version') != 1:
        raise ValueError('网关角色或接口版本不兼容')
    return {**result, 'elapsed_ms': round((time.monotonic() - started) * 1000)}


def submit(action, payload, business_key=None):
    start_worker()
    task_id = str(uuid.uuid4())
    now = time.time()
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        if business_key:
            row = db.execute('SELECT id FROM tasks WHERE business_key=?', (business_key,)).fetchone()
            if row:
                return row['id']
        db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)',
                   (task_id, business_key, action, json.dumps(payload, ensure_ascii=False),
                    'pending', '{}', '', now, now))
    _wake.set()
    return task_id


def result(task_id):
    with database() as db:
        row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if not row:
        raise ValueError('任务不存在')
    data = json.loads(row['result'])
    return {**data, 'success': row['state'] == 'succeeded', 'gateway_request_id': task_id,
            'gateway_state': row['state'],
            'error': data.get('error') or row['error'] or
                     ('' if row['state'] == 'succeeded' else 'MES 任务尚未成功，请查看通信任务状态')}


def deliver_once():
    cfg = config()
    with database() as db:
        pending = db.execute("SELECT * FROM tasks WHERE state != 'succeeded' ORDER BY CASE WHEN state='pending' THEN 0 ELSE 1 END, updated LIMIT 50").fetchall()
    with requests.Session() as session:
        session.trust_env = False
        session.headers['Authorization'] = 'Bearer ' + cfg['token']
        for task in pending:
            try:
                response = session.post(cfg['gateway_url'].rstrip('/') + '/api/tasks',
                    json={'id': task['id'], 'action': task['action'], 'payload': json.loads(task['payload'])},
                    timeout=(3, 5))
                response.raise_for_status()
                body = response.json()
                if body.get('id') != task['id'] or body.get('state') not in {
                    'accepted', 'waiting_manual', 'running', 'succeeded', 'failed', 'unknown'}:
                    raise ValueError('网关响应格式不正确')
                with database() as db:
                    db.execute('UPDATE tasks SET state=?,result=?,error=?,updated=? WHERE id=?',
                        (body['state'], json.dumps(body.get('result', {}), ensure_ascii=False), '', time.time(), task['id']))
                if body['state'] in {'succeeded', 'failed', 'unknown'}:
                    reconcile(task['id'])
            except Exception as exc:
                with database() as db:
                    db.execute('UPDATE tasks SET error=?,updated=? WHERE id=?', (str(exc), time.time(), task['id']))
                break


def reconcile(task_id):
    """Update audit results only; never write a historical result into current PLC bits."""
    from .models import MesRecord
    data = result(task_id)
    for record in MesRecord.objects.filter(success=False, response_payload__gateway_request_id=task_id):
        record.response_payload = data
        record.success = data['success']
        record.error_message = data.get('error', '')
        record.save(update_fields=['response_payload', 'success', 'error_message', 'updated_at'])


def _run():
    import logging
    from django.db import close_old_connections
    while True:
        try:
            close_old_connections()
            deliver_once()
        except Exception:
            logging.getLogger(__name__).exception('MES 网关后台通信异常')
        _wake.wait(2)
        _wake.clear()


def start_worker():
    global _started
    with _lock:
        if not _started:
            threading.Thread(target=_run, daemon=True, name='mes-gateway-transport').start()
            _started = True


class RemoteMesClient(MesClient):
    def _call(self, action, payload):
        # Include the packing cycle in mutation identity: rack codes are reusable.
        key = None
        if action != 'GET_RACK_RECIPE' or getattr(self, 'nonblocking', False):
            from apps.workflow.models import StationCycle
            cycle = StationCycle.objects.filter(rack__rack_code=payload.get('rack_code', '')).order_by('-pk').first()
            cycle_id = getattr(self, 'context_cycle', cycle.pk if cycle else None)
            payload = {**payload, '_packing_cycle': cycle_id}
            if getattr(self, 'context_request', None):
                payload['_input_request'] = self.context_request
            identity = {k: v for k, v in payload.items() if k != 'completed_at'}
            key = json.dumps([cycle_id, action, identity], sort_keys=True, ensure_ascii=False)
        task_id = submit(action, payload, key)
        if getattr(self, 'nonblocking', False):
            data = result(task_id)
            if data['gateway_state'] in {'pending', 'accepted', 'waiting_manual', 'running'}:
                raise RemotePending(task_id)
            return data
        deadline = time.monotonic() + float(config().get('wait_seconds', 20))
        while time.monotonic() < deadline:
            data = result(task_id)
            if data['gateway_state'] in {'succeeded', 'failed', 'unknown'}:
                return data
            time.sleep(0.15)
        return result(task_id)

    def retry_request(self, task_id):
        _wake.set()
        return result(task_id)

    def get_rack_recipe(self, rack_code):
        return self._call('GET_RACK_RECIPE', {'rack_code': rack_code})

    def upload_product_barcode(self, product_code, rack_code):
        return self._call('UPLOAD_PRODUCT_BARCODE', {'product_code': product_code, 'rack_code': rack_code})

    def upload_boxing_result(self, payload):
        return self._call('UPLOAD_BOXING_RESULT', payload)

    def upload_vision_result(self, payload):
        return {'success': False, 'error': 'MES 契约未提供视觉上传接口'}

    def upload_alarm(self, payload):
        return {'success': False, 'error': 'MES 契约未提供报警上传接口'}
