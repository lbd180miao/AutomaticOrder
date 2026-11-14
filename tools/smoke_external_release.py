import os,sys,json,sqlite3,shutil,socket,subprocess,time,urllib.request,uuid
from pathlib import Path
root=Path.cwd(); release=Path(sys.argv[1]).resolve(); data=root/'build'/('external-smoke-'+uuid.uuid4().hex[:8]);data.mkdir()
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
web,gateway=port(),port()
for name in ('db.sqlite3','deployment.json','agv_gateway.json','gateway.json'):shutil.copy2(release/name,data/name)
cfg=json.loads((data/'gateway.json').read_text());cfg.update(port=gateway,mes_url='http://127.0.0.1:1');(data/'gateway.json').write_text(json.dumps(cfg))
cfg=json.loads((data/'agv_gateway.json').read_text());cfg['gateway_url']=f'http://127.0.0.1:{gateway}';(data/'agv_gateway.json').write_text(json.dumps(cfg))
with sqlite3.connect(data/'db.sqlite3') as db:
 db.execute('UPDATE devices_device SET enabled=0')
env=dict(os.environ,AUTOMATIC_ORDER_REGISTER_STARTUP='false',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',RVC_CAMERA_AUTO_START='false',DM_CAMERA_AUTO_CONNECT='false',PLC_LISTENER_AUTO_START='true')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with (data/'console.log').open('wb') as log:
 p=subprocess.Popen([str(release/'ExternalControl.exe'),'--data-dir',str(data),'--port',str(web),'--no-browser'],env=env,cwd=data,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
 try:
  for _ in range(100):
   assert p.poll() is None,'EXE exited'
   try:
    with opener.open(f'http://127.0.0.1:{web}/devices/api/plc-status/?view=controls',timeout=2) as r:status=json.load(r)
    break
   except OSError:time.sleep(.5)
  else:raise RuntimeError('startup timeout')
  assert status['global_running'] is False,status
  with opener.open(f'http://127.0.0.1:{gateway}/',timeout=3) as r:assert r.status==200
  with opener.open(f'http://127.0.0.1:{web}/devices/status/',timeout=3) as r:
   page=r.read().decode('utf-8')
   assert 'DB2.DBX69.0' in page and 'DB2.DBB46' in page
  print('PASS external full app, gateway, no automatic PLC; logs:',data)
 finally:
  p.terminate();p.wait(timeout=15)
