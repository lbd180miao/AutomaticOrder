"""Standalone MES gateway project. No imports from the AGV project."""
import argparse
import hmac
import json
import logging
import sqlite3
import sys
import threading
import time
import uuid
import webbrowser
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from waitress import serve
from mes_client import YfpoSoapMesClient

ACTIONS = {'SELF_TEST', 'GET_RACK_RECIPE', 'UPLOAD_PRODUCT_BARCODE', 'UPLOAD_BOXING_RESULT'}


class Gateway:
    def __init__(self, directory, client=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.config = json.loads((self.directory / 'gateway.json').read_text(encoding='utf-8-sig'))
        if len(self.config.get('token', '')) < 24:
            raise ValueError('网关 token 至少需要 24 个字符')
        self.client = client or YfpoSoapMesClient(
            base_url=self.config['mes_url'], factory_code=self.config['factory_code'],
            prod_line_code=self.config['prod_line_code'], timeout=self.config.get('mes_timeout', 8),
            authorization=self.config.get('mes_authorization', ''),
            custom_headers=self.config.get('mes_headers', {}))
        self.wake = threading.Event()
        self.last_agv = None
        with self.db() as db:
            db.execute("UPDATE tasks SET state='unknown', result=? WHERE state='running'",
                       (json.dumps({'success': False, 'error': '网关执行期间重启，MES 结果需人工核对'}, ensure_ascii=False),))

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.directory / 'gateway.sqlite3', timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY, action TEXT, payload TEXT, state TEXT, result TEXT,
          created REAL, updated REAL)''')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def serialize(row):
        data = dict(row)
        data['payload'] = json.loads(data['payload'])
        data['result'] = json.loads(data['result'])
        return data

    def accept(self, body):
        task_id = str(uuid.UUID(body['id']))
        action = body['action']
        payload = body['payload']
        if action not in ACTIONS or not isinstance(payload, dict):
            raise ValueError('不支持的动作或请求内容')
        if action != 'SELF_TEST' and not str(payload.get('rack_code', '')).strip():
            raise ValueError('料框码不能为空')
        if action == 'UPLOAD_PRODUCT_BARCODE' and not str(payload.get('product_code', '')).strip():
            raise ValueError('产品条码不能为空')
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if existing:
                if existing['action'] != action or existing['payload'] != encoded:
                    raise ValueError('同一请求编号不能用于不同内容')
                return self.serialize(existing)
            now = time.time()
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?)',
                       (task_id, action, encoded, 'accepted', '{}', now, now))
            row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        self.wake.set()
        return self.serialize(row)

    def execute_once(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM tasks WHERE state='accepted' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return False
            db.execute("UPDATE tasks SET state='running',updated=? WHERE id=?", (time.time(), row['id']))
        payload = json.loads(row['payload'])
        action = row['action']
        try:
            if action == 'SELF_TEST':
                result = {'success': True, 'message': '网关已接收、落库并完成自检；未调用 MES 或 PLC', 'request_id': row['id']}
            elif action == 'GET_RACK_RECIPE':
                result = self.client.get_rack_recipe(payload['rack_code'])
            elif action == 'UPLOAD_PRODUCT_BARCODE':
                result = self.client.upload_product_barcode(payload['product_code'], payload['rack_code'])
            else:
                # The SOAP seal action sends RackCode only; all local products must be bound first.
                codes = set(payload.get('product_codes') or [])
                with self.db() as db:
                    bindings = db.execute("SELECT payload,state FROM tasks WHERE action='UPLOAD_PRODUCT_BARCODE'").fetchall()
                bound = set()
                for binding in bindings:
                    p = json.loads(binding['payload'])
                    if (p.get('rack_code') == payload['rack_code'] and
                        p.get('_packing_cycle') == payload.get('_packing_cycle') and binding['state'] == 'succeeded'):
                        bound.add(p.get('product_code'))
                if not codes or not codes.issubset(bound):
                    result = {'success': False, 'business': True, 'error': '本批次单件绑定尚未全部成功，禁止封箱'}
                else:
                    result = self.client.upload_boxing_result(payload)
            if result.get('success') is True:
                state = 'succeeded'
            elif result.get('business') or action == 'GET_RACK_RECIPE':
                state = 'failed'
            else:
                state = 'unknown'
        except Exception as exc:
            logging.exception('MES execution failed')
            state = 'unknown' if action.startswith('UPLOAD_') else 'failed'
            result = {'success': False, 'error': str(exc)}
        with self.db() as db:
            db.execute('UPDATE tasks SET state=?,result=?,updated=? WHERE id=?',
                       (state, json.dumps(result, ensure_ascii=False, default=str), time.time(), row['id']))
        return True

    def worker(self):
        while True:
            try:
                if self.execute_once():
                    continue
            except Exception:
                logging.exception('Gateway worker failed')
            self.wake.wait(1)
            self.wake.clear()

    def __call__(self, env, start_response):
        def reply(status, data, content_type='application/json; charset=utf-8'):
            raw = data.encode('utf-8') if isinstance(data, str) else json.dumps(data, ensure_ascii=False).encode('utf-8')
            start_response(status, [('Content-Type', content_type), ('Content-Length', str(len(raw))),
                                    ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')])
            return [raw]
        path = env.get('PATH_INFO', '/')
        local = env.get('REMOTE_ADDR') in {'127.0.0.1', '::1'}
        try:
            if path == '/' and local:
                return reply('200 OK', (Path(__file__).parent / 'web.html').read_text(encoding='utf-8'), 'text/html; charset=utf-8')
            if path == '/app.css' and local:
                return reply('200 OK', (Path(__file__).parent / 'app.css').read_text(encoding='utf-8'), 'text/css; charset=utf-8')
            if path.startswith('/local/'):
                if not local:
                    return reply('403 Forbidden', {'error': '管理界面仅允许本机访问'})
                if env['REQUEST_METHOD'] == 'POST' and env.get('HTTP_ORIGIN') not in {
                    'http://127.0.0.1:' + str(self.config.get('port', 8000)),
                    'http://localhost:' + str(self.config.get('port', 8000))}:
                    return reply('403 Forbidden', {'error': '请求来源不正确'})
                if path == '/local/config':
                    if env['REQUEST_METHOD'] == 'GET':
                        return reply('200 OK', {k: self.config.get(k, '') for k in
                            ['mes_url','factory_code','prod_line_code','mes_timeout']})
                    if env['REQUEST_METHOD'] == 'POST':
                        size = int(env.get('CONTENT_LENGTH') or 0)
                        if not 0 < size <= 16384:
                            raise ValueError('配置大小不合法')
                        body = json.loads(env['wsgi.input'].read(size))
                        address = str(body.get('mes_url', '')).strip()
                        if urlparse(address).scheme not in {'http','https'} or not urlparse(address).hostname:
                            raise ValueError('请输入有效 MES HTTP/HTTPS 地址')
                        timeout = int(body.get('mes_timeout', 8))
                        if not 1 <= timeout <= 120:
                            raise ValueError('超时范围为 1 至 120 秒')
                        new = {**self.config, 'mes_url':address, 'mes_timeout':timeout,
                               'factory_code':str(body.get('factory_code','')).strip(),
                               'prod_line_code':str(body.get('prod_line_code','')).strip()}
                        if not new['factory_code'] or not new['prod_line_code']:
                            raise ValueError('工厂编码和产线编码不能为空')
                        if body.get('mes_authorization'):
                            new['mes_authorization'] = str(body['mes_authorization'])
                        temporary = self.directory / ('gateway-' + uuid.uuid4().hex + '.tmp')
                        temporary.write_text(json.dumps(new,ensure_ascii=False,indent=2),encoding='utf-8')
                        temporary.replace(self.directory / 'gateway.json')
                        return reply('200 OK', {'success':True,'message':'配置已保存，重启网关后生效；空白认证保留原值'})
                if path == '/local/query' and env['REQUEST_METHOD'] == 'POST':
                    size = int(env.get('CONTENT_LENGTH') or 0)
                    if not 0 < size <= 4096:
                        raise ValueError('请求大小不合法')
                    body = json.loads(env['wsgi.input'].read(size))
                    code = str(body.get('rack_code','')).strip()
                    if not code or len(code)>64 or not code.isascii():
                        raise ValueError('请输入 1 至 64 位 ASCII 料框码')
                    return reply('200 OK', self.accept({'id':str(uuid.uuid4()),'action':'GET_RACK_RECIPE',
                        'payload':{'rack_code':code,'_source':'gateway_manual_query'}}))
                if path == '/local/records' and env['REQUEST_METHOD'] == 'GET':
                    query = parse_qs(env.get('QUERY_STRING',''))
                    page = max(1,int(query.get('page',['1'])[0]))
                    clauses, values = [], []
                    for key in ['action','state']:
                        value = query.get(key,[''])[0]
                        if value:
                            if key == 'state' and value == 'attention':
                                clauses.append("state IN ('failed','unknown')")
                            else:
                                clauses.append(key+'=?'); values.append(value)
                    keyword=query.get('q',[''])[0]
                    if keyword:
                        clauses.append('(id LIKE ? OR payload LIKE ? OR result LIKE ?)')
                        values.extend(['%'+keyword+'%']*3)
                    where=' WHERE '+' AND '.join(clauses) if clauses else ''
                    with self.db() as db:
                        total=db.execute('SELECT count(*) FROM tasks'+where,values).fetchone()[0]
                        tasks=[self.serialize(r) for r in db.execute('SELECT * FROM tasks'+where+' ORDER BY created DESC LIMIT 30 OFFSET ?',values+[(page-1)*30])]
                        counts=dict(db.execute('SELECT state,count(*) FROM tasks GROUP BY state').fetchall())
                        db.execute('CREATE TABLE IF NOT EXISTS resolutions (task_id TEXT, resolution TEXT, note TEXT, previous_result TEXT, created REAL)')
                        audit=[dict(r) for r in db.execute('SELECT * FROM resolutions ORDER BY created DESC LIMIT 100')]
                    return reply('200 OK',{'tasks':tasks,'total':total,'page':page,'counts':counts,'audit':audit})
                if path == '/local/status' and env['REQUEST_METHOD'] == 'GET':
                    with self.db() as db:
                        tasks = [self.serialize(r) for r in db.execute('SELECT * FROM tasks ORDER BY created DESC LIMIT 100')]
                    return reply('200 OK', {'mes_url': self.config['mes_url'], 'last_agv': self.last_agv,
                                           'factory_code': self.config['factory_code'], 'prod_line_code': self.config['prod_line_code'], 'tasks': tasks})
                if path == '/local/mes-test' and env['REQUEST_METHOD'] == 'POST':
                    if env.get('HTTP_ORIGIN') not in {'http://127.0.0.1:' + str(self.config.get('port', 8000)), 'http://localhost:' + str(self.config.get('port', 8000))}:
                        return reply('403 Forbidden', {'error': '请求来源不正确'})
                    # Load WSDL only. No binding/sealing or other MES business calls.
                    self.client._get_client()
                    return reply('200 OK', {'success': True, 'message': 'MES WSDL 加载成功；尚未验证业务接口或业务权限'})
                if path == '/local/resolve' and env['REQUEST_METHOD'] == 'POST':
                    if env.get('HTTP_ORIGIN') != 'http://127.0.0.1:' + str(self.config.get('port', 8000)):
                        return reply('403 Forbidden', {'error': '请通过本机 127.0.0.1 页面操作'})
                    length = int(env.get('CONTENT_LENGTH') or 0)
                    if not 0 < length <= 16384:
                        raise ValueError('请求大小不合法')
                    body = json.loads(env['wsgi.input'].read(length))
                    note = str(body.get('note', '')).strip()
                    if len(note) < 5 or body.get('resolution') not in {'verified_success', 'verified_not_executed'}:
                        raise ValueError('需要填写至少 5 个字符的 MES 核对记录')
                    with self.db() as db:
                        db.execute('BEGIN IMMEDIATE')
                        row = db.execute('SELECT * FROM tasks WHERE id=?', (body['id'],)).fetchone()
                        if not row or row['state'] not in {'failed', 'unknown'}:
                            raise ValueError('只有失败或待核对任务允许处理')
                        if row['action'] == 'GET_RACK_RECIPE' and body['resolution'] == 'verified_success':
                            raise ValueError('料框查询必须获取真实 MES 返回值，请选择重新查询')
                        db.execute('CREATE TABLE IF NOT EXISTS resolutions (task_id TEXT, resolution TEXT, note TEXT, previous_result TEXT, created REAL)')
                        db.execute('INSERT INTO resolutions VALUES (?,?,?,?,?)', (body['id'], body['resolution'], note, row['result'], time.time()))
                        if body['resolution'] == 'verified_success':
                            result = {'success': True, 'manually_verified': True, 'message': note, 'bin_code': str(body.get('bin_code', ''))}
                            db.execute("UPDATE tasks SET state='succeeded',result=?,updated=? WHERE id=?", (json.dumps(result, ensure_ascii=False), time.time(), body['id']))
                        else:
                            db.execute("UPDATE tasks SET state='accepted',result='{}',updated=? WHERE id=?", (time.time(), body['id']))
                    self.wake.set()
                    return reply('200 OK', {'success': True, 'message': '核对结果已保存；AGV 自动同步结果，PLC 工位需按现场流程解除锁定'})
                return reply('404 Not Found', {'error': '接口不存在'})
            supplied = env.get('HTTP_AUTHORIZATION', '')
            if not hmac.compare_digest(supplied, 'Bearer ' + self.config['token']):
                return reply('401 Unauthorized', {'error': '网关认证失败'})
            self.last_agv = time.time()
            if path == '/api/health' and env['REQUEST_METHOD'] == 'GET':
                return reply('200 OK', {'success': True, 'role': 'mes_gateway', 'version': 1})
            if path == '/api/tasks' and env['REQUEST_METHOD'] == 'POST':
                length = int(env.get('CONTENT_LENGTH') or 0)
                if not 0 < length <= 1024 * 1024:
                    return reply('413 Payload Too Large', {'error': '请求大小不合法'})
                data = json.loads(env['wsgi.input'].read(length))
                return reply('200 OK', self.accept(data))
            return reply('404 Not Found', {'error': '接口不存在'})
        except (ValueError, KeyError, TypeError) as exc:
            return reply('400 Bad Request', {'success': False, 'error': str(exc)})
        except Exception as exc:
            logging.exception('Gateway request error')
            return reply('500 Internal Server Error', {'success': False, 'error': str(exc)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir')
    parser.add_argument('--port', type=int)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    directory = Path(args.data_dir) if args.data_dir else (Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent)
    from instance_lock import acquire
    directory.mkdir(parents=True, exist_ok=True)
    instance_handle = acquire(directory)
    app = Gateway(directory)
    port = args.port or app.config.get('port', 8000)
    app.config['port'] = port
    (directory / 'logs').mkdir(exist_ok=True)
    logging.basicConfig(filename=directory / 'logs' / 'gateway.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')
    threading.Thread(target=app.worker, daemon=True).start()
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(f'http://127.0.0.1:{port}')).start()
    serve(app, host='0.0.0.0', port=port, threads=8)


if __name__ == '__main__':
    main()
