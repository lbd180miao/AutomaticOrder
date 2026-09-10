import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")  # 改成你的项目名

import django
django.setup()

from waitress import serve
from django.core.wsgi import get_wsgi_application

serve(get_wsgi_application(), host="127.0.0.1", port=8000)
