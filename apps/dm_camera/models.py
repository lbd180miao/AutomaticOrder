"""
DM相机数据模型
"""
from django.db import models
from django.utils import timezone


class DMCameraConfig(models.Model):
    """DM相机配置模型"""
    
    name = models.CharField('配置名称', max_length=100, unique=True)
    device_sn = models.CharField('设备序列号', max_length=32, blank=True)
    
    # 采集参数
    frame_rate = models.IntegerField('帧率', default=10, help_text='帧/秒')
    exposure_time = models.IntegerField('曝光时间', default=1000, help_text='微秒')
    trigger_mode = models.CharField(
        '触发模式',
        max_length=20,
        default='ACTIVE',
        choices=[
            ('ACTIVE', '主动模式'),
            ('SOFT', '软触发'),
            ('HARD', '硬触发'),
        ]
    )
    
    # 滤波参数
    confidence_filter_enable = models.BooleanField('置信度滤波', default=True)
    confidence_threshold = models.IntegerField('置信度阈值', default=15)
    
    flying_pixels_filter_enable = models.BooleanField('飞点滤波', default=True)
    flying_pixels_threshold = models.IntegerField('飞点阈值', default=5)
    
    spatial_filter_enable = models.BooleanField('空间滤波', default=True)
    spatial_threshold = models.IntegerField('空间阈值', default=5)
    
    # 元数据
    is_active = models.BooleanField('是否激活', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    
    class Meta:
        db_table = 'dm_camera_config'
        verbose_name = 'DM相机配置'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({'激活' if self.is_active else '未激活'})"


class DMCaptureRecord(models.Model):
    """DM相机采集记录"""
    
    FRAME_TYPE_CHOICES = [
        ('DEPTH', '深度图'),
        ('IR', 'IR图'),
        ('POINTCLOUD', '点云'),
        ('RGB', 'RGB图'),
    ]
    
    config = models.ForeignKey(
        DMCameraConfig,
        on_delete=models.CASCADE,
        related_name='capture_records',
        verbose_name='使用配置'
    )
    
    frame_type = models.CharField('帧类型', max_length=20, choices=FRAME_TYPE_CHOICES)
    frame_index = models.IntegerField('帧序号', default=0)
    
    # 数据信息
    width = models.IntegerField('宽度')
    height = models.IntegerField('高度')
    temperature_chip = models.FloatField('芯片温度', null=True, blank=True)
    temperature_laser1 = models.FloatField('激光器1温度', null=True, blank=True)
    temperature_laser2 = models.FloatField('激光器2温度', null=True, blank=True)
    
    # 文件路径
    data_file = models.FileField('数据文件', upload_to='dm_camera/captures/%Y/%m/%d/', null=True, blank=True)
    preview_image = models.ImageField('预览图', upload_to='dm_camera/previews/%Y/%m/%d/', null=True, blank=True)
    
    # 元数据
    metadata = models.JSONField('元数据', default=dict, blank=True)
    captured_at = models.DateTimeField('采集时间', default=timezone.now)
    
    class Meta:
        db_table = 'dm_camera_capture'
        verbose_name = 'DM采集记录'
        verbose_name_plural = verbose_name
        ordering = ['-captured_at']
        indexes = [
            models.Index(fields=['-captured_at']),
            models.Index(fields=['frame_type']),
        ]
    
    def __str__(self):
        return f"{self.frame_type} - {self.captured_at.strftime('%Y-%m-%d %H:%M:%S')}"


class DMCameraSession(models.Model):
    """DM相机会话管理"""
    
    STATUS_CHOICES = [
        ('IDLE', '空闲'),
        ('CONNECTED', '已连接'),
        ('STREAMING', '采集中'),
        ('ERROR', '错误'),
    ]
    
    device_sn = models.CharField('设备序列号', max_length=32)
    device_ip = models.GenericIPAddressField('设备IP', null=True, blank=True)
    
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='IDLE')
    error_message = models.TextField('错误信息', blank=True)
    
    config = models.ForeignKey(
        DMCameraConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sessions',
        verbose_name='使用配置'
    )
    
    connected_at = models.DateTimeField('连接时间', null=True, blank=True)
    disconnected_at = models.DateTimeField('断开时间', null=True, blank=True)
    
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    
    class Meta:
        db_table = 'dm_camera_session'
        verbose_name = 'DM相机会话'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.device_sn} - {self.get_status_display()}"
