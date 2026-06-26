from django.contrib import admin

from .models import (
    CalibrationProfile,
    FoamInspectionResult,
    RackLocationROI3D,
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


@admin.register(RackLocationROI3D)
class RackLocationROI3DAdmin(admin.ModelAdmin):
    list_display = (
        'roi_name', 'recipe', 'mode', 'layer_no', 'coordinate_system',
        'x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max', 'enabled',
    )
    list_filter = ('enabled', 'mode', 'coordinate_system', 'layer_no')
    search_fields = ('roi_name', 'recipe__recipe_name')


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
