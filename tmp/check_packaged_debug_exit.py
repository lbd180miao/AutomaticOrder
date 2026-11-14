import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AutomaticOrder.settings')
import django
django.setup()
from PyInstaller.archive.readers import CArchiveReader
import apps.workflow.station_service as module
archive = CArchiveReader('delivery/20261113-AutoMES-Communication/AGVControl/AGVControl.exe')
code = archive.open_embedded_archive('PYZ.pyz').extract('apps.workflow.station_service')
exec(code, module.__dict__)
from django.test.runner import DiscoverRunner
labels = ['apps.workflow.tests_debug_exit.DebugExitRegressionTests.' + n for n in (
    'test_close_debug_during_five_second_high', 'test_close_debug_discards_saved_camera_jobs')]
raise SystemExit(bool(DiscoverRunner(verbosity=2, interactive=False).run_tests(labels)))
