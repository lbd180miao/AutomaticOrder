"""Request-matched manual replies and durable gateway communication audit."""
import json
import time
import uuid
import hashlib

BUSINESS_ACTIONS = ('GET_RACK_RECIPE', 'UPLOAD_PRODUCT_BARCODE', 'UPLOAD_BOXING_RESULT')


def schema(db):
    db.execute("CREATE TABLE IF NOT EXISTS communication_modes (action TEXT PRIMARY KEY, mode TEXT NOT NULL)")
    db.execute("""CREATE TABLE IF NOT EXISTS communication_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_key TEXT UNIQUE, task_id TEXT,
        direction TEXT, kind TEXT, data TEXT, created REAL)""")


def event(db, task_id, direction, kind, data, *, once=False):
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True)
    key = hashlib.sha256((str(task_id)+kind+encoded).encode()).hexdigest() if once else str(uuid.uuid4())
    db.execute('INSERT OR IGNORE INTO communication_events (event_key,task_id,direction,kind,data,created) VALUES (?,?,?,?,?,?)',
               (key, task_id, direction, kind, encoded, time.time()))


class CommunicationMixin:
    def communication_status(self):
        with self.db() as db:
            modes = dict(db.execute('SELECT action,mode FROM communication_modes'))
            tasks = [self.serialize(row) for row in db.execute('SELECT * FROM tasks ORDER BY created DESC LIMIT 100')]
            waiting = [self.serialize(row) for row in db.execute("SELECT * FROM tasks WHERE state='waiting_manual' ORDER BY created")]
            events = [dict(row) for row in db.execute('SELECT task_id,direction,kind,data,created FROM communication_events ORDER BY id DESC LIMIT 200')]
        for row in events:
            row['data'] = json.loads(row['data'])
        return {'success': True, 'modes': {a:modes.get(a, 'auto') for a in BUSINESS_ACTIONS},
                'tasks': tasks, 'waiting': waiting, 'events': events}

    def set_communication_mode(self, action, mode):
        if action not in BUSINESS_ACTIONS or mode not in ('auto', 'manual'):
            raise ValueError('请选择有效接口及自动/手动模式')
        with self.db() as db:
            db.execute('INSERT INTO communication_modes VALUES (?,?) ON CONFLICT(action) DO UPDATE SET mode=excluded.mode', (action, mode))
            event(db, '', '操作记录', 'mode_changed', {'action':action, 'mode':mode})
        return {'success': True, 'action':action, 'mode':mode,
                'message':'已切换，适用于新请求；已等待手动返回的任务继续等待手动处理'}

    def manual_reply(self, body):
        if not isinstance(body, dict) or not isinstance(body.get('id'), str):
            raise ValueError('请求编号无效')
        task_id = str(uuid.UUID(body['id']))
        result = body.get('result')
        if not isinstance(result, dict) or type(result.get('success')) is not bool:
            raise ValueError('返回值必须包含布尔型 success')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if row is None or row['state'] != 'waiting_manual':
                raise ValueError('只能向等待手动返回的请求发送一次结果')
            if body.get('action') != row['action']:
                raise ValueError('返回接口与请求接口不一致')
            payload = json.loads(row['payload'])
            if result.get('rack_code') and result['rack_code'] != payload['rack_code']:
                raise ValueError('返回料框码与原请求不一致')
            result = dict(result, rack_code=payload['rack_code'], response_source='manual',
                          request_id=task_id)
            if result['success']:
                field = {'GET_RACK_RECIPE':'pkg_type_code', 'UPLOAD_BOXING_RESULT':'bin_code'}.get(row['action'])
                if field:
                    value = result.get(field)
                    if not isinstance(value, str) or not value.strip() or len(value) > 128:
                        raise ValueError('成功返回必须填写 ' + field)
                    result[field] = value.strip()
            else:
                if not isinstance(result.get('error'), str) or not result['error'].strip():
                    raise ValueError('失败返回必须填写原因')
                result['business'] = True
            if row['action'] == 'UPLOAD_PRODUCT_BARCODE':
                result['product_code'] = payload['product_code']
            state = 'succeeded' if result['success'] else 'failed'
            db.execute('UPDATE tasks SET state=?,result=?,updated=? WHERE id=?',
                       (state,json.dumps(result,ensure_ascii=False),time.time(),task_id))
            event(db, task_id, '外部电脑 → AGV', 'manual_reply', result)
        self.wake.set()
        return {'success':True, 'id':task_id, 'state':state, 'result':result,
                'message':'返回结果已保存，AGV 下次 HTTP 同步时接收'}
