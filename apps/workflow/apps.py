from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.workflow'
    verbose_name = '流程编排'

    def ready(self):
        import os
        import sys
        # Only the serving runserver process. EXE/Waitress starts explicitly
        # in run.py; management commands and camera workers must never poll PLC.
        if 'runserver' in sys.argv and (
            '--noreload' in sys.argv or os.environ.get('RUN_MAIN') == 'true'
        ):
            from .listener import start_listener
            start_listener()
