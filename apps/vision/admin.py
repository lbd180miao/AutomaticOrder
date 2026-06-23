from django.contrib import admin

from .models import (
    CalibrationProfile,
    FoamInspectionResult,
    RackLocationRecipe,
    RackLocationResult,
    VisionImage,
    VisionRecipe,
    VisionTask,
)


admin.site.register(VisionTask)
@admin.register(RackLocationRecipe)
class RackLocationRecipeAdmin(admin.ModelAdmin):
    list_display = (
        'recipe_name', 'position_no', 'layer_no', 'rack_side',
        'standard_x', 'standard_y', 'standard_z', 'confidence_threshold', 'enabled',
    )
    list_filter = ('enabled', 'rack_side', 'layer_no')
    search_fields = ('recipe_name', 'rack_type', 'capture_pose_name')


@admin.register(RackLocationResult)
class RackLocationResultAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'position_no', 'layer_no', 'side', 'is_success',
        'actual_x', 'actual_y', 'actual_z',
        'offset_x', 'offset_y', 'offset_z', 'confidence', 'plc_write_status', 'created_at',
    )
    list_filter = ('is_success', 'plc_write_status', 'side', 'layer_no')
    search_fields = ('error_code', 'error_message', 'raw_data_path', 'result_image_path')

admin.site.register(FoamInspectionResult)
admin.site.register(VisionImage)
admin.site.register(CalibrationProfile)
admin.site.register(VisionRecipe)
