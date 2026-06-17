from django.contrib import admin

from .models import WorkflowEvent, WorkflowInstance


admin.site.register(WorkflowInstance)
admin.site.register(WorkflowEvent)
