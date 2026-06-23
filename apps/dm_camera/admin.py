"""
DM相机Django Admin配置
"""
from django.contrib import admin
from .models import DMCameraConfig, DMCaptureRecord, DMCameraSession


@admin.register(DMCameraConfig)
class DMCameraConfigAdmin(admin.ModelAdmin):
    """DM相机配置管理"""
    list_display = ['name', 'device_sn', 'frame_rate', 'trigger_mode', 'is_active', 'created_at']
    list_filter = ['is_active', 'trigger_mode', 'created_at']
    search_fields = ['name', 'device_sn']
    ordering = ['-created_at']
    
    fieldsets = (
        ('基本信息', {
            'fields': ('name', 'device_sn', 'is_active')
        }),
        ('采集参数', {
            'fields': ('frame_rate', 'exposure_time', 'trigger_mode')
        }),
        ('滤波参数', {
            'fields': (
                ('confidence_filter_enable', 'confidence_threshold'),
                ('flying_pixels_filter_enable', 'flying_pixels_threshold'),
                ('spatial_filter_enable', 'spatial_threshold'),
            ),
            'classes': ('collapse',),
        }),
    )


@admin.register(DMCaptureRecord)
class DMCaptureRecordAdmin(admin.ModelAdmin):
    """DM采集记录管理"""
    list_display = ['id', 'frame_type', 'frame_index', 'width', 'height', 
                   'temperature_chip', 'captured_at']
    list_filter = ['frame_type', 'captured_at']
    search_fields = ['frame_index']
    date_hierarchy = 'captured_at'
    ordering = ['-captured_at']
    readonly_fields = ['captured_at', 'preview_image', 'data_file']
    
    fieldsets = (
        ('基本信息', {
            'fields': ('config', 'frame_type', 'frame_index', 'captured_at')
        }),
        ('数据信息', {
            'fields': ('width', 'height', 'temperature_chip', 'temperature_laser1', 
                      'temperature_laser2')
        }),
        ('文件', {
            'fields': ('preview_image', 'data_file'),
        }),
        ('元数据', {
            'fields': ('metadata',),
            'classes': ('collapse',),
        }),
    )


@admin.register(DMCameraSession)
class DMCameraSessionAdmin(admin.ModelAdmin):
    """DM相机会话管理"""
    list_display = ['id', 'device_sn', 'device_ip', 'status', 'connected_at', 
                   'disconnected_at']
    list_filter = ['status', 'connected_at']
    search_fields = ['device_sn', 'device_ip']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('设备信息', {
            'fields': ('device_sn', 'device_ip', 'config')
        }),
        ('状态信息', {
            'fields': ('status', 'error_message')
        }),
        ('时间信息', {
            'fields': ('connected_at', 'disconnected_at', 'created_at', 'updated_at')
        }),
    )
