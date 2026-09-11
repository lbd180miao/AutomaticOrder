import os
import whitenoise.middleware   # 强制打包 whitenoise 子模块

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "AutomaticOrder.settings")  # 改成你的项目名

import django
django.setup()

from waitress import serve
from django.core.wsgi import get_wsgi_application

serve(get_wsgi_application(), host="127.0.0.1", port=8000)
