import sys, json
sys.path.insert(0, '.venv/Lib/site-packages')
import chg_hik

camera = chg_hik.Camera(
    output_dir='d:/workspace2/AutomaticOrder/media/hik_captures',
    format='PNG',
    quality=5
)

camera.open()
print('capture start', flush=True)
try:
    path = camera.capture()
    print('capture done:', path, flush=True)
    camera.close_camera()
except Exception as e:
    print('ERROR:', repr(e), flush=True)
