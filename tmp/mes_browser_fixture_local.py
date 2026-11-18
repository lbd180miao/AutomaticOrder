import os,sys,json,uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
sys.path.insert(0,str(Path.cwd()))
os.environ['DJANGO_SETTINGS_MODULE']='AutomaticOrder.settings'
import django
django.setup()
from django.template.loader import render_to_string
from django.contrib.staticfiles import finders
rows=[dict(id=str(uuid.uuid4()),action='GET_RACK_RECIPE',state='succeeded',created=1794708000-i,payload={'rack_code':'TEST-%02d'%i},result={'success':True,'mes_data':{'PkgTypeCode':'2LayerRack','Items':['TEST-%02d'%j for j in range(45)]}}) for i in range(25)]
class Page(BaseHTTPRequestHandler):
 def do_GET(self):
  path=self.path.split('?')[0]
  if path.startswith('/static/') and '..' not in path:
   f=finders.find(path[8:])
   if not f: return self.send_error(404)
   import mimetypes
   data=Path(f).read_bytes(); mime=mimetypes.guess_type(f)[0] or 'application/octet-stream'
  elif path=='/mes/communication/':
   data=render_to_string('mes/communication_page.html').encode();mime='text/html; charset=utf-8'
  else:
   task=next((r for r in rows if r['id'] in path),rows[0])
   events=[dict(kind=k,created=task['created']+i,data={'state':'succeeded'}) for i,k in enumerate(['queued','request_received','mes_request','mes_response','gateway_response'])]
   data=json.dumps(dict(success=True,task=task,events=events) if '/records/' in path else dict(connected=True,tasks=rows,events=[])).encode();mime='application/json'
  self.send_response(200);self.send_header('Content-Type',mime);self.end_headers();self.wfile.write(data)
HTTPServer(('127.0.0.1',18742),Page).serve_forever()
