"""Django test runner that keeps factory hardware diagnostics opt-in."""

from django.conf import settings
from django.test.runner import DiscoverRunner


class ApplicationDiscoverRunner(DiscoverRunner):
    """Discover application tests without importing root-level SDK scripts."""

    def build_suite(self, test_labels=None, **kwargs):
        if not test_labels:
            test_labels = [
                app_name
                for app_name in settings.INSTALLED_APPS
                if app_name.startswith('apps.')
            ]
        return super().build_suite(test_labels=test_labels, **kwargs)
