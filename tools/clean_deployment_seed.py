"""Remove visual history only from the build snapshot, never the source DB."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
import django
django.setup()
from django.db import connection, transaction
from apps.vision.models import VisionTask, RackLayerMeasurement

expected = (ROOT / 'build/distributed_seed/db.sqlite3').resolve()
if Path(connection.settings_dict['NAME']).resolve() != expected:
    raise RuntimeError('Refusing to clean anything except the deployment snapshot')
with transaction.atomic():
    tasks, _ = VisionTask.objects.all().delete()
    measurements, _ = RackLayerMeasurement.objects.all().delete()
with connection.cursor() as cursor:
    cursor.execute('PRAGMA temp_store=MEMORY')
    cursor.execute('VACUUM')
    cursor.execute('PRAGMA foreign_key_check')
    if cursor.fetchall():
        raise RuntimeError('Deployment snapshot has broken foreign keys')
print(f'Removed {tasks} visual task/result/image rows and {measurements} measurement rows from build snapshot.')
