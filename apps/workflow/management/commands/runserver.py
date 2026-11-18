"""Start PLC polling once the Django development server is listening."""
from django.contrib.staticfiles.management.commands.runserver import Command as StaticfilesRunserver


class Command(StaticfilesRunserver):
    def on_bind(self, server_port):
        super().on_bind(server_port)
        from apps.workflow.listener import start_listener
        start_listener()
        from apps.devices.health import start_monitor
        start_monitor()

    def inner_run(self, *args, **options):
        from apps.workflow.listener import stop_listener
        try:
            return super().inner_run(*args, **options)
        finally:
            from apps.devices.health import stop_monitor
            stop_monitor()
            stop_listener()
