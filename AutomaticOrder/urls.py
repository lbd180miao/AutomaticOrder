from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.core.urls')),
    path('production/', include('apps.production.urls')),
    path('workflow/', include('apps.workflow.urls')),
    path('devices/', include('apps.devices.urls')),
    path('vision/', include('apps.vision.urls')),
    path('mes/', include('apps.mes.urls')),
    path('alarms/', include('apps.alarms.urls')),
    path('traceability/', include('apps.traceability.urls')),
    path('dm-camera/', include('apps.dm_camera.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
