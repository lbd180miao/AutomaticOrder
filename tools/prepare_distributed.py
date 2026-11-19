"""Prepare reproducible, separate AGV and gateway deployment directories."""
import json
import secrets
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'build' / 'distributed_seed'
STAGE.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(ROOT / 'db.sqlite3') as source, sqlite3.connect(STAGE / 'db.sqlite3') as dest:
    source.backup(dest)

spec = (ROOT / 'MyApp.spec').read_text(encoding='utf-8')
spec = spec.replace("('db.sqlite3', '.')", "('build/distributed_seed/db.sqlite3', '.')")
spec = spec.replace("name='MyApp'", "name='AGVControl'")
spec = spec.replace('bundle_visual_data = True', 'bundle_visual_data = False')
(ROOT / 'AGVControl.spec').write_text(spec, encoding='utf-8')

# Both releases receive the same random pairing secret; never print it.
pairing = STAGE / 'pairing.json'
if not pairing.exists():
    pairing.write_text(json.dumps({'token': secrets.token_urlsafe(36)}), encoding='utf-8')
token = json.loads(pairing.read_text())['token']
(STAGE / 'agv_gateway.json').write_text(json.dumps({
    'gateway_url': 'http://192.168.3.10:8001', 'token': token, 'wait_seconds': 20,
}, ensure_ascii=False, indent=2), encoding='utf-8')
(STAGE / 'gateway.json').write_text(json.dumps({
    'port': 8001, 'token': token,
    'mes_url': 'http://10.252.165.162/MESService/BaseService.svc?singleWsdl',
    'factory_code': '1060', 'prod_line_code': 'I308', 'mes_timeout': 8,
    'mes_authorization': '', 'mes_headers': {},
}, ensure_ascii=False, indent=2), encoding='utf-8')
print('Prepared database snapshot, independent build spec and paired configuration.')
