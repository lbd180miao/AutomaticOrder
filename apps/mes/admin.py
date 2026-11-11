from django.contrib import admin

from .models import MesRecord, PkgTypeMapping


admin.site.register(MesRecord)


@admin.register(PkgTypeMapping)
class PkgTypeMappingAdmin(admin.ModelAdmin):
    list_display = ('pkg_type_code', 'rack_type', 'plc_value', 'enabled', 'updated_at')
    list_filter = ('rack_type', 'plc_value', 'enabled')
    search_fields = ('pkg_type_code',)
    list_editable = ('rack_type', 'plc_value', 'enabled')
