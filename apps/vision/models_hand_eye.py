"""
手眼标定数据模型
用于管理3D深度相机与机器人之间的坐标转换关系
"""
from django.db import models
from django.core.exceptions import ValidationError
from apps.core.models import TimeStampedModel


class HandEyeCalibration(TimeStampedModel):
    """
    手眼标定参数模型
    
    存储相机坐标系到机器人法兰坐标系的固定变换矩阵 T_flange_camera
    标定完成后该矩阵固定不变，直到重新标定
    """
    
    CALIBRATION_METHOD_CHOICES = [
        ('OPENCV_TSAI', 'OpenCV Tsai-Lenz方法'),
        ('OPENCV_PARK', 'OpenCV Park方法'),
        ('OPENCV_HORAUD', 'OpenCV Horaud方法'),
        ('OPENCV_ANDREFF', 'OpenCV Andreff方法'),
        ('OPENCV_DANIILIDIS', 'OpenCV Daniilidis方法'),
        ('MANUAL', '手动输入'),
        ('VENDOR_TOOL', '厂商工具'),
    ]
    
    name = models.CharField('标定名称', max_length=128, unique=True, 
                           help_text='例如：装箱机器人-DM相机-20260101')
    
    # 关联设备
    robot_device = models.ForeignKey(
        'devices.Device',
        on_delete=models.CASCADE,
        related_name='hand_eye_calibrations_robot',
        verbose_name='机器人设备',
        help_text='关联的机器人设备'
    )
    camera_device = models.ForeignKey(
        'devices.Device',
        on_delete=models.CASCADE,
        related_name='hand_eye_calibrations_camera',
        verbose_name='相机设备',
        help_text='关联的3D深度相机设备'
    )
    
    # 手眼标定矩阵 T_flange_camera (4×4齐次变换矩阵)
    # 存储格式：{"matrix": [[r11, r12, r13, tx], [r21, r22, r23, ty], [r31, r32, r33, tz], [0, 0, 0, 1]]}
    T_flange_camera = models.JSONField(
        '手眼标定矩阵',
        default=dict,
        help_text='相机坐标系到机器人法兰坐标系的4×4齐次变换矩阵'
    )
    
    # 标定质量指标
    calibration_error = models.FloatField(
        '标定误差',
        default=0.0,
        help_text='标定重投影误差（单位：mm）'
    )
    sample_count = models.IntegerField(
        '样本数量',
        default=0,
        help_text='用于标定的样本姿态数量'
    )
    
    # 标定方法和参数
    calibration_method = models.CharField(
        '标定方法',
        max_length=32,
        choices=CALIBRATION_METHOD_CHOICES,
        default='OPENCV_TSAI'
    )
    calibration_params = models.JSONField(
        '标定参数',
        default=dict,
        blank=True,
        help_text='标定过程的详细参数记录'
    )
    
    # 状态管理
    is_active = models.BooleanField(
        '是否激活',
        default=False,
        help_text='当前激活的标定配置，每组机器人-相机只能有一个激活的标定'
    )
    verified_at = models.DateTimeField(
        '验证时间',
        null=True,
        blank=True,
        help_text='标定验证通过的时间'
    )
    
    # 备注信息
    description = models.TextField('描述', blank=True)
    operator = models.CharField('操作员', max_length=64, blank=True)
    
    class Meta:
        db_table = 'vision_hand_eye_calibration'
        verbose_name = '手眼标定'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['robot_device', 'camera_device', 'is_active']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['robot_device', 'camera_device'],
                condition=models.Q(is_active=True),
                name='unique_active_calibration_per_robot_camera'
            ),
        ]
    
    def __str__(self):
        active = '✓' if self.is_active else ''
        return f"{self.name} {active}"
    
    def clean(self):
        """验证标定矩阵格式"""
        super().clean()
        errors = {}
        
        # 验证T_flange_camera格式
        if self.T_flange_camera:
            if 'matrix' not in self.T_flange_camera:
                errors['T_flange_camera'] = '缺少matrix字段'
            else:
                matrix = self.T_flange_camera['matrix']
                if not isinstance(matrix, list) or len(matrix) != 4:
                    errors['T_flange_camera'] = '矩阵必须是4×4格式'
                else:
                    for i, row in enumerate(matrix):
                        if not isinstance(row, list) or len(row) != 4:
                            errors['T_flange_camera'] = f'第{i+1}行必须包含4个元素'
                            break
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        # 如果设置为激活，取消同组机器人-相机的其他激活标定
        if self.is_active:
            HandEyeCalibration.objects.filter(
                robot_device=self.robot_device,
                camera_device=self.camera_device,
                is_active=True
            ).exclude(id=self.id).update(is_active=False)
        
        self.full_clean()
        super().save(*args, **kwargs)


class HandEyeCalibrationSample(TimeStampedModel):
    """
    手眼标定样本数据
    
    记录每个标定姿态下的：
    1. 机器人位姿 (T_base_flange)
    2. 标定板在相机坐标系下的位姿 (T_camera_target)
    """
    
    calibration = models.ForeignKey(
        HandEyeCalibration,
        on_delete=models.CASCADE,
        related_name='samples',
        verbose_name='所属标定'
    )
    
    sample_index = models.IntegerField(
        '样本序号',
        help_text='样本采集顺序'
    )
    
    # 机器人法兰在基坐标系下的位姿
    # 存储格式：{"matrix": [[...], [...], [...], [...]]} 或 {"x": 0, "y": 0, "z": 0, "rx": 0, "ry": 0, "rz": 0}
    T_base_flange = models.JSONField(
        '机器人位姿',
        help_text='机器人法兰在基坐标系下的4×4变换矩阵或六自由度位姿'
    )
    
    # 标定板在相机坐标系下的位姿
    # 存储格式：{"matrix": [[...], [...], [...], [...]]} 或 {"rvec": [...], "tvec": [...]}
    T_camera_target = models.JSONField(
        '标定板位姿',
        help_text='标定板在相机坐标系下的位姿（OpenCV格式或4×4矩阵）'
    )
    
    # 采集数据
    capture_record = models.ForeignKey(
        'dm_camera.DMCaptureRecord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hand_eye_samples',
        verbose_name='采集记录'
    )
    
    # 质量指标
    detection_success = models.BooleanField(
        '检测成功',
        default=True,
        help_text='标定板特征点是否成功检测'
    )
    reprojection_error = models.FloatField(
        '重投影误差',
        default=0.0,
        help_text='该样本的特征点重投影误差（单位：像素）'
    )
    
    # 备注
    notes = models.TextField('备注', blank=True)
    
    class Meta:
        db_table = 'vision_hand_eye_sample'
        verbose_name = '手眼标定样本'
        verbose_name_plural = verbose_name
        ordering = ['calibration', 'sample_index']
        indexes = [
            models.Index(fields=['calibration', 'sample_index']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['calibration', 'sample_index'],
                name='unique_sample_index_per_calibration'
            ),
        ]
    
    def __str__(self):
        return f"{self.calibration.name} - 样本{self.sample_index}"
    
    def clean(self):
        """验证位姿数据格式"""
        super().clean()
        errors = {}
        
        # 验证T_base_flange格式
        if self.T_base_flange:
            if 'matrix' in self.T_base_flange:
                # 矩阵格式
                matrix = self.T_base_flange['matrix']
                if not isinstance(matrix, list) or len(matrix) != 4:
                    errors['T_base_flange'] = '矩阵必须是4×4格式'
            elif not all(k in self.T_base_flange for k in ['x', 'y', 'z', 'rx', 'ry', 'rz']):
                errors['T_base_flange'] = '六自由度格式必须包含x,y,z,rx,ry,rz字段'
        
        # 验证T_camera_target格式
        if self.T_camera_target:
            if 'matrix' not in self.T_camera_target and \
               ('rvec' not in self.T_camera_target or 'tvec' not in self.T_camera_target):
                errors['T_camera_target'] = '必须包含matrix字段或rvec+tvec字段'
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class HandEyeVerificationResult(TimeStampedModel):
    """
    手眼标定验证结果
    
    使用标定结果转换测试点云，对比实际坐标，评估标定质量
    """
    
    calibration = models.ForeignKey(
        HandEyeCalibration,
        on_delete=models.CASCADE,
        related_name='verification_results',
        verbose_name='所属标定'
    )
    
    # 验证位姿
    T_base_flange = models.JSONField(
        '机器人位姿',
        help_text='验证时的机器人位姿'
    )
    
    # 验证点
    test_points_camera = models.JSONField(
        '相机坐标点',
        help_text='相机坐标系下的测试点'
    )
    test_points_robot = models.JSONField(
        '机器人坐标点',
        help_text='转换后的机器人坐标系点'
    )
    ground_truth_points = models.JSONField(
        '真实坐标点',
        default=list,
        blank=True,
        help_text='已知的真实坐标（如有）'
    )
    
    # 误差统计
    mean_error = models.FloatField(
        '平均误差',
        default=0.0,
        help_text='平均位置误差（单位：mm）'
    )
    max_error = models.FloatField(
        '最大误差',
        default=0.0,
        help_text='最大位置误差（单位：mm）'
    )
    std_error = models.FloatField(
        '标准差',
        default=0.0,
        help_text='误差标准差（单位：mm）'
    )
    
    # 验证结果
    is_passed = models.BooleanField(
        '是否通过',
        default=False,
        help_text='验证是否通过（误差在阈值内）'
    )
    error_threshold = models.FloatField(
        '误差阈值',
        default=5.0,
        help_text='验证通过的误差阈值（单位：mm）'
    )
    
    # 备注
    notes = models.TextField('备注', blank=True)
    
    class Meta:
        db_table = 'vision_hand_eye_verification'
        verbose_name = '手眼标定验证'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['calibration', '-created_at']),
        ]
    
    def __str__(self):
        status = '✓' if self.is_passed else '✗'
        return f"{self.calibration.name} 验证 {status} (误差: {self.mean_error:.2f}mm)"
