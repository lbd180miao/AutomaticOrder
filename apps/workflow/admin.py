from django.contrib import admin

from .models import StationCycle, WorkflowEvent, WorkflowInstance


admin.site.register(WorkflowInstance)
admin.site.register(WorkflowEvent)
admin.site.register(StationCycle)
