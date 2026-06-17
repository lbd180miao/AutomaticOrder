from django.contrib import admin

from .models import CalibrationProfile, FoamInspectionResult, RackLocationResult, VisionImage, VisionTask


admin.site.register(VisionTask)
admin.site.register(RackLocationResult)
admin.site.register(FoamInspectionResult)
admin.site.register(VisionImage)
admin.site.register(CalibrationProfile)
