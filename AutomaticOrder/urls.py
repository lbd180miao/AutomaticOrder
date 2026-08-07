"""
URL configuration for AutomaticOrder project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.core.urls')),
    # [已从导航移除] 生产管理 - 与装箱上位机业务场景无关
    # path('production/', include('apps.production.urls')),
    path('workflow/', include('apps.workflow.urls')),
    path('devices/', include('apps.devices.urls')),
    path('vision/', include('apps.vision.urls')),
    # [已从导航移除] 坐标工作台 - 调试工具，已合并入视觉模块
    # transform-roi 功能已迁移至 vision:api_coord_transform_roi
    # path('coordinates/', include('apps.coordinates.urls')),
    path('mes/', include('apps.mes.urls')),
    path('alarms/', include('apps.alarms.urls')),
    # [已从导航移除] 追溯查询 - 条码追溯由MES系统负责，非本上位机职责
    # path('traceability/', include('apps.traceability.urls')),
    path('dm-camera/', include('apps.dm_camera.urls')),  # DM 3D深度相机
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
