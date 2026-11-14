import os, sys, threading, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for key in ('PLC_LISTENER_AUTO_START','RVC_CAMERA_AUTO_START','DM_CAMERA_AUTO_CONNECT'):
    os.environ[key]='false'
os.environ.setdefault('DJANGO_SETTINGS_MODULE','AutomaticOrder.settings')
import django
django.setup()
from django.core.wsgi import get_wsgi_application
from waitress import create_server
server=create_server(get_wsgi_application(),host='127.0.0.1',port=0,threads=2)
threading.Thread(target=server.run,daemon=True).start()
try:
    base=f'http://127.0.0.1:{server.effective_port}'
    for path, expected in [('/vision/foam-inspector/','原图上传上限 128 MB'),('/static/vision/js/foam_recipe_summary.js','foamDecisionSummary')]:
        with urllib.request.urlopen(base+path,timeout=15) as response:
            assert response.status==200 and expected in response.read().decode()
    print('PASS: Waitress workbench, 128 MB limit and static assets.')
finally:
    server.close()
