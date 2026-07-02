"""
手眼标定服务
使用OpenCV calibrateHandEye实现相机到机器人的坐标转换标定
"""
import numpy as np
import cv2
import logging
from typing import List, Dict, Tuple, Optional
from django.utils import timezone
from django.db import transaction

from .models_hand_eye import (
    HandEyeCalibration, 
    HandEyeCalibrationSample,
    HandEyeVerificationResult
)
from .coordinate_transform import CoordinateTransformService

logger = logging.getLogger(__name__)


class HandEyeCalibrationService:
    """
    手眼标定服务
    
    核心功能：
    1. 采集标定样本（机器人位姿 + 标定板位姿）
    2. 使用OpenCV计算手眼标定矩阵 T_flange_camera
    3. 验证标定结果
    """
    
    # OpenCV支持的标定方法
    CALIBRATION_METHODS = {
        'OPENCV_TSAI': cv2.CALIB_HAND_EYE_TSAI,
        'OPENCV_PARK': cv2.CALIB_HAND_EYE_PARK,
        'OPENCV_HORAUD': cv2.CALIB_HAND_EYE_HORAUD,
        'OPENCV_ANDREFF': cv2.CALIB_HAND_EYE_ANDREFF,
        'OPENCV_DANIILIDIS': cv2.CALIB_HAND_EYE_DANIILIDIS,
    }
    
    def __init__(self):
        self.transform_service = CoordinateTransformService()
    
    @transaction.atomic
    def create_calibration(
        self,
        name: str,
        robot_device_id: int,
        camera_device_id: int,
        description: str = '',
        operator: str = ''
    ) -> HandEyeCalibration:
        """
        创建新的手眼标定任务
        
        Args:
            name: 标定名称
            robot_device_id: 机器人设备ID
            camera_device_id: 相机设备ID
            description: 描述
            operator: 操作员
            
        Returns:
            HandEyeCalibration实例
        """
        from apps.devices.models import Device
        
        robot_device = Device.objects.get(id=robot_device_id)
        camera_device = Device.objects.get(id=camera_device_id)
        
        calibration = HandEyeCalibration.objects.create(
            name=name,
            robot_device=robot_device,
            camera_device=camera_device,
            description=description,
            operator=operator,
            T_flange_camera={'matrix': np.eye(4).tolist()},  # 初始化为单位矩阵
            is_active=False
        )
        
        logger.info(f"创建手眼标定任务: {name}")
        return calibration
    
    @transaction.atomic
    def add_sample(
        self,
        calibration_id: int,
        T_base_flange: Dict,
        T_camera_target: Dict,
        capture_record_id: Optional[int] = None,
        detection_success: bool = True,
        reprojection_error: float = 0.0,
        notes: str = ''
    ) -> HandEyeCalibrationSample:
        """
        添加一个标定样本
        
        Args:
            calibration_id: 标定任务ID
            T_base_flange: 机器人位姿（字典格式）
            T_camera_target: 标定板在相机坐标系下的位姿
            capture_record_id: 采集记录ID（可选）
            detection_success: 检测是否成功
            reprojection_error: 重投影误差
            notes: 备注
            
        Returns:
            HandEyeCalibrationSample实例
        """
        calibration = HandEyeCalibration.objects.get(id=calibration_id)
        
        # 计算样本序号
        last_sample = calibration.samples.order_by('-sample_index').first()
        sample_index = (last_sample.sample_index + 1) if last_sample else 1
        
        sample = HandEyeCalibrationSample.objects.create(
            calibration=calibration,
            sample_index=sample_index,
            T_base_flange=T_base_flange,
            T_camera_target=T_camera_target,
            capture_record_id=capture_record_id,
            detection_success=detection_success,
            reprojection_error=reprojection_error,
            notes=notes
        )
        
        logger.info(f"添加标定样本 #{sample_index} 到 {calibration.name}")
        return sample
    
    def compute_calibration(
        self,
        calibration_id: int,
        method: str = 'OPENCV_TSAI'
    ) -> Dict:
        """
        使用OpenCV calibrateHandEye计算手眼标定矩阵
        
        Args:
            calibration_id: 标定任务ID
            method: 标定方法
            
        Returns:
            计算结果字典
            
        Raises:
            ValueError: 样本数量不足或标定失败
        """
        calibration = HandEyeCalibration.objects.get(id=calibration_id)
        samples = calibration.samples.filter(detection_success=True).order_by('sample_index')
        
        if samples.count() < 3:
            raise ValueError(f"标定样本数量不足，至少需要3个样本，当前有{samples.count()}个")
        
        # 准备数据
        R_gripper2base_list = []  # 机器人位姿的旋转部分
        t_gripper2base_list = []  # 机器人位姿的平移部分
        R_target2cam_list = []    # 标定板位姿的旋转部分
        t_target2cam_list = []    # 标定板位姿的平移部分
        
        for sample in samples:
            # 解析机器人位姿
            T_base_flange = self.transform_service.parse_matrix_from_json(sample.T_base_flange)
            R_gripper2base_list.append(T_base_flange[:3, :3])
            t_gripper2base_list.append(T_base_flange[:3, 3:4])  # (3, 1)
            
            # 解析标定板位姿
            T_camera_target = self.transform_service.parse_matrix_from_json(sample.T_camera_target)
            R_target2cam_list.append(T_camera_target[:3, :3])
            t_target2cam_list.append(T_camera_target[:3, 3:4])  # (3, 1)
        
        # 调用OpenCV标定
        opencv_method = self.CALIBRATION_METHODS.get(method, cv2.CALIB_HAND_EYE_TSAI)
        
        try:
            R_cam2gripper, t_cam2gripper = cv2.calibrateHandEye(
                R_gripper2base=R_gripper2base_list,
                t_gripper2base=t_gripper2base_list,
                R_target2cam=R_target2cam_list,
                t_target2cam=t_target2cam_list,
                method=opencv_method
            )
            
            # 构造4×4齐次变换矩阵
            T_flange_camera = np.eye(4, dtype=np.float64)
            T_flange_camera[:3, :3] = R_cam2gripper
            T_flange_camera[:3, 3] = t_cam2gripper.flatten()
            
            # 验证旋转矩阵
            is_valid, msg = self.transform_service.validate_rotation_matrix(R_cam2gripper)
            if not is_valid:
                logger.warning(f"标定结果旋转矩阵验证失败: {msg}")
            
            # 计算标定误差（重投影误差）
            calibration_error = self._compute_reprojection_error(
                samples, T_flange_camera
            )
            
            # 保存结果
            calibration.T_flange_camera = self.transform_service.matrix_to_json(T_flange_camera)
            calibration.calibration_method = method
            calibration.sample_count = samples.count()
            calibration.calibration_error = calibration_error
            calibration.calibration_params = {
                'method': method,
                'opencv_method_code': int(opencv_method),
                'sample_count': samples.count(),
                'rotation_valid': is_valid,
                'rotation_check_message': msg
            }
            calibration.save()
            
            logger.info(f"标定计算完成: {calibration.name}, 误差={calibration_error:.4f}mm")
            
            return {
                'success': True,
                'T_flange_camera': T_flange_camera.tolist(),
                'calibration_error': calibration_error,
                'sample_count': samples.count(),
                'method': method,
                'rotation_valid': is_valid,
                'message': f"标定成功，误差={calibration_error:.4f}mm"
            }
            
        except Exception as e:
            logger.error(f"标定计算失败: {str(e)}", exc_info=True)
            raise ValueError(f"标定计算失败: {str(e)}")
    
    def _compute_reprojection_error(
        self,
        samples,
        T_flange_camera: np.ndarray
    ) -> float:
        """
        计算标定的重投影误差
        
        对每个样本：
        1. 用标定结果 T_flange_camera 和机器人位姿 T_base_flange 计算标定板在基坐标系的位置
        2. 与实际观测的标定板位置比较
        3. 计算平均误差
        
        Args:
            samples: 标定样本查询集
            T_flange_camera: 标定矩阵
            
        Returns:
            平均重投影误差（mm）
        """
        errors = []
        
        for sample in samples:
            try:
                T_base_flange = self.transform_service.parse_matrix_from_json(sample.T_base_flange)
                T_camera_target = self.transform_service.parse_matrix_from_json(sample.T_camera_target)
                
                # 标定板中心在相机坐标系
                target_center_cam = T_camera_target[:3, 3]
                
                # 使用标定结果转换到机器人基坐标系
                target_center_base_computed = self.transform_service.camera_to_robot_base(
                    target_center_cam,
                    T_flange_camera,
                    T_base_flange
                )
                
                # 理想情况下，所有样本的标定板在基坐标系的位置应该一致
                # 这里计算与第一个样本的偏差
                if not errors:
                    # 第一个样本作为参考
                    self._reference_position = target_center_base_computed
                
                error = np.linalg.norm(target_center_base_computed - self._reference_position)
                errors.append(error)
                
            except Exception as e:
                logger.warning(f"计算样本 {sample.sample_index} 误差失败: {str(e)}")
                continue
        
        return float(np.mean(errors)) if errors else 0.0
    
    @transaction.atomic
    def verify_calibration(
        self,
        calibration_id: int,
        T_base_flange: Dict,
        test_points_camera: List[List[float]],
        ground_truth_points: Optional[List[List[float]]] = None,
        error_threshold: float = 5.0,
        notes: str = ''
    ) -> HandEyeVerificationResult:
        """
        验证手眼标定结果
        
        Args:
            calibration_id: 标定任务ID
            T_base_flange: 验证位姿（机器人位姿）
            test_points_camera: 相机坐标系测试点列表 [[x, y, z], ...]
            ground_truth_points: 真实坐标点（可选）
            error_threshold: 误差阈值（mm）
            notes: 备注
            
        Returns:
            HandEyeVerificationResult实例
        """
        calibration = HandEyeCalibration.objects.get(id=calibration_id)
        
        # 解析矩阵
        T_flange_camera = self.transform_service.parse_matrix_from_json(calibration.T_flange_camera)
        T_base_flange_matrix = self.transform_service.parse_matrix_from_json(T_base_flange)
        
        # 转换测试点
        test_points_camera_array = np.array(test_points_camera, dtype=np.float64)
        test_points_robot = self.transform_service.camera_to_robot_base(
            test_points_camera_array,
            T_flange_camera,
            T_base_flange_matrix
        )
        
        # 计算误差
        mean_error = 0.0
        max_error = 0.0
        std_error = 0.0
        is_passed = True
        
        if ground_truth_points is not None:
            ground_truth_array = np.array(ground_truth_points, dtype=np.float64)
            errors = np.linalg.norm(test_points_robot - ground_truth_array, axis=1)
            
            mean_error = float(np.mean(errors))
            max_error = float(np.max(errors))
            std_error = float(np.std(errors))
            is_passed = mean_error <= error_threshold
        
        # 保存验证结果
        verification = HandEyeVerificationResult.objects.create(
            calibration=calibration,
            T_base_flange=T_base_flange,
            test_points_camera=test_points_camera,
            test_points_robot=test_points_robot.tolist(),
            ground_truth_points=ground_truth_points or [],
            mean_error=mean_error,
            max_error=max_error,
            std_error=std_error,
            is_passed=is_passed,
            error_threshold=error_threshold,
            notes=notes
        )
        
        logger.info(f"标定验证完成: {calibration.name}, 平均误差={mean_error:.2f}mm, 通过={is_passed}")
        
        # 如果验证通过，更新标定的验证时间
        if is_passed:
            calibration.verified_at = timezone.now()
            calibration.save(update_fields=['verified_at'])
        
        return verification
    
    @transaction.atomic
    def activate_calibration(self, calibration_id: int) -> HandEyeCalibration:
        """
        激活指定的标定配置
        
        同一组机器人-相机只能有一个激活的标定
        
        Args:
            calibration_id: 标定任务ID
            
        Returns:
            HandEyeCalibration实例
        """
        calibration = HandEyeCalibration.objects.get(id=calibration_id)
        calibration.is_active = True
        calibration.save()  # save方法中会自动处理同组的其他标定
        
        logger.info(f"激活标定配置: {calibration.name}")
        return calibration
    
    def get_active_calibration(
        self,
        robot_device_id: int,
        camera_device_id: int
    ) -> Optional[HandEyeCalibration]:
        """
        获取指定机器人-相机组合的激活标定配置
        
        Args:
            robot_device_id: 机器人设备ID
            camera_device_id: 相机设备ID
            
        Returns:
            HandEyeCalibration实例或None
        """
        return HandEyeCalibration.objects.filter(
            robot_device_id=robot_device_id,
            camera_device_id=camera_device_id,
            is_active=True
        ).first()
    
    def delete_sample(self, sample_id: int) -> bool:
        """
        删除标定样本
        
        Args:
            sample_id: 样本ID
            
        Returns:
            是否成功删除
        """
        try:
            sample = HandEyeCalibrationSample.objects.get(id=sample_id)
            calibration_name = sample.calibration.name
            sample_index = sample.sample_index
            sample.delete()
            
            logger.info(f"删除标定样本: {calibration_name} 样本#{sample_index}")
            return True
        except HandEyeCalibrationSample.DoesNotExist:
            return False
    
    @transaction.atomic
    def clear_samples(self, calibration_id: int) -> int:
        """
        清空指定标定的所有样本
        
        Args:
            calibration_id: 标定任务ID
            
        Returns:
            删除的样本数量
        """
        calibration = HandEyeCalibration.objects.get(id=calibration_id)
        count = calibration.samples.count()
        calibration.samples.all().delete()
        
        logger.info(f"清空标定样本: {calibration.name}, 共删除{count}个样本")
        return count
    
    def export_calibration(self, calibration_id: int) -> Dict:
        """
        导出标定配置（用于备份或迁移）
        
        Args:
            calibration_id: 标定任务ID
            
        Returns:
            标定配置字典
        """
        calibration = HandEyeCalibration.objects.get(id=calibration_id)
        
        export_data = {
            'name': calibration.name,
            'robot_device_code': calibration.robot_device.code,
            'camera_device_code': calibration.camera_device.code,
            'T_flange_camera': calibration.T_flange_camera,
            'calibration_method': calibration.calibration_method,
            'calibration_error': calibration.calibration_error,
            'sample_count': calibration.sample_count,
            'calibration_params': calibration.calibration_params,
            'description': calibration.description,
            'operator': calibration.operator,
            'created_at': calibration.created_at.isoformat(),
            'verified_at': calibration.verified_at.isoformat() if calibration.verified_at else None,
        }
        
        return export_data
    
    @transaction.atomic
    def import_calibration(
        self,
        import_data: Dict,
        robot_device_id: int,
        camera_device_id: int
    ) -> HandEyeCalibration:
        """
        导入标定配置
        
        Args:
            import_data: 导出的标定数据
            robot_device_id: 目标机器人设备ID
            camera_device_id: 目标相机设备ID
            
        Returns:
            HandEyeCalibration实例
        """
        from apps.devices.models import Device
        
        robot_device = Device.objects.get(id=robot_device_id)
        camera_device = Device.objects.get(id=camera_device_id)
        
        calibration = HandEyeCalibration.objects.create(
            name=import_data['name'],
            robot_device=robot_device,
            camera_device=camera_device,
            T_flange_camera=import_data['T_flange_camera'],
            calibration_method=import_data.get('calibration_method', 'MANUAL'),
            calibration_error=import_data.get('calibration_error', 0.0),
            sample_count=import_data.get('sample_count', 0),
            calibration_params=import_data.get('calibration_params', {}),
            description=import_data.get('description', ''),
            operator=import_data.get('operator', ''),
            is_active=False
        )
        
        logger.info(f"导入标定配置: {calibration.name}")
        return calibration
