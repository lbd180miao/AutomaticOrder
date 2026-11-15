"""Read the latest paired-computer request from the local communication ledger."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from django.conf import settings


def latest_communication_log():
    actions = {'GET_RACK_RECIPE': '查询料框类型', 'UPLOAD_PRODUCT_BARCODE': '产品绑定',
               'UPLOAD_BOXING_RESULT': '装箱完成'}
    states = {'pending': '等待发送', 'accepted': '已接收', 'running': '处理中',
              'waiting_manual': '等待人工处理', 'succeeded': '成功', 'failed': '失败',
              'unknown': '结果待核对'}
    candidates = []
    for filename in ('mes_outbox.sqlite3', 'gateway.sqlite3'):
        path = settings.DATA_DIR / filename
        if not path.is_file():
            continue
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='tasks'").fetchone():
                continue
            row = db.execute('SELECT * FROM tasks ORDER BY created DESC, id DESC LIMIT 1').fetchone()
            if row:
                candidates.append(dict(row))
    if not candidates:
        return []
    row = max(candidates, key=lambda item: (item['created'], item['updated']))
    result = json.loads(row['result'] or '{}')
    error = row.get('error') or result.get('error')
    level = 'ERROR' if error or row['state'] == 'failed' else 'WARN' if row['state'] == 'unknown' else 'INFO'
    message = ' · '.join(str(part) for part in (actions.get(row['action'], row['action']),
                         states.get(row['state'], row['state']), error, row['id']) if part)
    return [(datetime.fromtimestamp(row['updated'], timezone.utc), level, 'AGV ↔ 外部电脑', message)]
