"""
DM相机业务逻辑服务层
"""
import os
import io
import atexit
import logging
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

import numpy as np
from PIL import Image
from django.core.files.base import ContentFile
from django.utils import timezone
from django.conf import settings

from .models import DMCameraConfig, DMCaptureRecord, DMCameraSession
from .sdk_wrapper import DMCamera, DMCameraConfigurationError, DMCameraException, DeviceInfo
from .sdk.LW_DM_Type import LWTriggerMode, LWFrameType, LWDataRecvType
from .tofconfig import TofConfigError, load_tof_config

logger = logging.getLogger(__name__)


class DMCameraService:
    """DM相机服务类 - 单例模式"""
    
    _instance = None
    _camera: Optional[DMCamera] = None
    _current_session: Optional[DMCameraSession] = None
    _atexit_registered = False

    @classmethod
    def _release_on_exit(cls):
        """进程退出时强制释放相机。

        网络 ToF 相机同一时刻只允许一个会话；若进程（含 Django autoreload
        重启、Ctrl+C）退出时未调用 LWCloseDevice，相机会一直被这条已死的
        会话占用，下次再开就报 "device already occupied"。此处兜底关闭。
        """
        inst = cls._instance
        if inst is None or inst._camera is None:
            return
        try:
            inst._camera.disconnect()
        except Exception:  # noqa: BLE001 - 退出清理，任何异常都忽略
            pass
        inst._camera = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._camera is not None and self._camera.device_handle is not None
    
    @property
    def is_streaming(self) -> bool:
        """是否正在采集"""
        return self._camera is not None and self._camera.is_streaming
    
    def find_devices(self) -> List[Dict]:
        """
        查找所有可用的DM相机设备
        
        Returns:
            设备信息列表
        """
        try:
            temp_camera = DMCamera()
            devices = temp_camera.find_devices()
            
            result = []
            for device in devices:
                result.append({
                    'handle': device.handle,
                    'sn': device.sn,
                    'type': device.type,
                    'ip': device.ip,
                    'local_ip': device.local_ip,
                })
            
            return result
        except DMCameraException as e:
            logger.error(f"查找设备失败: {str(e)}")
            raise
    
    def connect(self, device_sn: Optional[str] = None, config_id: Optional[int] = None) -> Dict:
        """
        连接到DM相机
        
        Args:
            device_sn: 设备序列号，为None时连接第一个设备
            config_id: 配置ID，为None时使用激活的配置
            
        Returns:
            连接信息
        """
        try:
            # 先释放任何旧 SDK 实例；即使未连接成功，旧实例析构也会清理 SDK 全局资源。
            if self._camera is not None:
                self.disconnect()
            
            # 创建相机实例
            self._camera = DMCamera()
            
            # 查找并连接设备
            devices = self._camera.find_devices()
            if not devices:
                raise DMCameraException("未找到可用设备")
            
            # 选择设备
            target_device = None
            if device_sn:
                for device in devices:
                    if device.sn == device_sn:
                        target_device = device
                        break
                if target_device is None:
                    raise DMCameraException(f"未找到序列号为 {device_sn} 的设备")
            else:
                target_device = devices[0]
            
            # 连接设备
            connected_device = self._camera.connect(target_device)
            
            # 获取或创建配置
            if config_id:
                config = DMCameraConfig.objects.get(id=config_id)
            else:
                config = DMCameraConfig.objects.filter(is_active=True).first()
                if not config:
                    # 创建默认配置
                    config = DMCameraConfig.objects.create(
                        name='默认配置',
                        is_active=True
                    )
            
            # 应用配置
            self._apply_config(config)
            
            # 创建会话记录
            self._current_session = DMCameraSession.objects.create(
                device_sn=connected_device.sn,
                device_ip=connected_device.ip,
                status='CONNECTED',
                config=config,
                connected_at=timezone.now()
            )
            
            logger.info(f"成功连接到设备: {connected_device.sn}")

            # 进程退出兜底释放，避免相机被已死会话长期占用。
            if not DMCameraService._atexit_registered:
                atexit.register(DMCameraService._release_on_exit)
                DMCameraService._atexit_registered = True

            return {
                'device_sn': connected_device.sn,
                'device_type': connected_device.type,
                'device_ip': connected_device.ip,
                'config_name': config.name,
                'session_id': self._current_session.id
            }
        
        except Exception as e:  # noqa: BLE001 - 设备打开后的任何失败都必须释放 SDK 资源
            logger.error(f"连接设备失败: {str(e)}")
            if self._current_session:
                self._current_session.status = 'ERROR'
                self._current_session.error_message = str(e)
                self._current_session.save()
            if self._camera is not None:
                try:
                    self._camera.disconnect()
                except Exception:  # noqa: BLE001 - 连接失败后的资源清理不能覆盖原始错误
                    pass
                self._camera = None
            raise
    
    def disconnect(self):
        """断开相机连接"""
        disconnect_error = None
        try:
            if self._camera:
                try:
                    self._camera.disconnect()
                except DMCameraException as e:
                    disconnect_error = e

            session = self._current_session
            self._camera = None
            self._current_session = None

            if session:
                session.status = 'ERROR' if disconnect_error else 'IDLE'
                session.disconnected_at = timezone.now()
                if disconnect_error:
                    session.error_message = str(disconnect_error)
                session.save()

            if disconnect_error:
                raise disconnect_error

            logger.info("设备已断开连接")
        
        except DMCameraException as e:
            logger.error(f"断开设备失败: {str(e)}")
            raise
    
    def _apply_config(self, config: DMCameraConfig):
        """应用相机配置"""
        if not self.is_connected:
            raise DMCameraException("设备未连接")
        
        # 映射触发模式
        try:
            tof_config = load_tof_config()
        except TofConfigError as e:
            raise DMCameraConfigurationError(f"tofconfig configuration error: {e}") from e

        trigger_mode_map = {
            'ACTIVE': LWTriggerMode.LW_TRIGGER_ACTIVE,
            'SOFT': LWTriggerMode.LW_TRIGGER_SOFT,
            'HARD': LWTriggerMode.LW_TRIGGER_HARD,
        }
        try:
            trigger_mode = trigger_mode_map[tof_config.trigger_mode]
        except KeyError as e:
            raise DMCameraConfigurationError(
                f"invalid tofconfig trigger_mode: {tof_config.trigger_mode}"
            ) from e
        
        # 配置相机
        self._camera.configure_camera(
            frame_rate=tof_config.frame_rate,
            exposure_time=tof_config.exposure_time,
            trigger_mode=trigger_mode,
        )
        
        # 配置滤波器
        self._camera.set_filters(
            confidence=tof_config.confidence,
            flying_pixels=tof_config.flying_pixels,
            spatial=tof_config.spatial,
        )
        
        logger.info(f"已应用配置: {config.name}")
    
    def start_stream(self) -> Dict:
        """开启数据流"""
        if not self.is_connected:
            raise DMCameraException("设备未连接")
        
        try:
            self._camera.start_stream(LWDataRecvType.LW_DEPTH_IR_RTY)
            
            if self._current_session:
                self._current_session.status = 'STREAMING'
                self._current_session.save()
            
            logger.info("数据流已开启")
            return {'status': 'streaming', 'message': '数据流已开启'}
        
        except DMCameraException as e:
            logger.error(f"开启数据流失败: {str(e)}")
            if self._current_session:
                self._current_session.status = 'ERROR'
                self._current_session.error_message = str(e)
                self._current_session.save()
            raise
    
    def stop_stream(self) -> Dict:
        """停止数据流"""
        if not self.is_connected:
            raise DMCameraException("设备未连接")
        
        try:
            self._camera.stop_stream()
            
            if self._current_session:
                self._current_session.status = 'CONNECTED'
                self._current_session.save()
            
            logger.info("数据流已停止")
            return {'status': 'connected', 'message': '数据流已停止'}
        
        except DMCameraException as e:
            logger.error(f"停止数据流失败: {str(e)}")
            raise
    
    def capture(self, frame_type: str = 'DEPTH', save_record: bool = True) -> Dict:
        """
        捕获一帧数据
        
        Args:
            frame_type: 帧类型 ('DEPTH', 'IR', 'POINTCLOUD')
            save_record: 是否保存记录到数据库
            
        Returns:
            捕获结果
        """
        if not self.is_streaming:
            raise DMCameraException("数据流未开启")
        
        try:
            # 映射帧类型
            frame_type_map = {
                'DEPTH': LWFrameType.LW_DEPTH_FRAME,
                'IR': LWFrameType.LW_IR_FRAME,
                'POINTCLOUD': LWFrameType.LW_POINTCLOUD_FRAME,
            }
            
            lw_frame_type = frame_type_map.get(frame_type, LWFrameType.LW_DEPTH_FRAME)
            
            # 捕获帧
            frame_data = self._camera.capture_frame(lw_frame_type)
            
            # 构建结果
            result = {
                'frame_type': frame_type,
                'width': frame_data.width,
                'height': frame_data.height,
                'frame_index': frame_data.frameIndex,
                'timestamp': {
                    'sec': frame_data.timestamp.sec,
                    'usec': frame_data.timestamp.usec
                },
                'temperature': {
                    'chip': frame_data.temperature.chip,
                    'laser1': frame_data.temperature.laser1,
                    'laser2': frame_data.temperature.laser2,
                } if frame_data.temperature else None,
            }
            
            # 保存记录
            if save_record and self._current_session:
                record = self._save_capture_record(frame_data, frame_type)
                result['record_id'] = record.id
                result['preview_url'] = record.preview_image.url if record.preview_image else None
            
            logger.info(f"成功捕获 {frame_type} 帧，序号: {frame_data.frameIndex}")
            return result
        
        except DMCameraException as e:
            logger.error(f"捕获帧失败: {str(e)}")
            raise

    def capture_frame_data(self, frame_type: str = 'DEPTH', save_record: bool = True) -> Dict:
        """捕获一帧并返回后端算法可直接使用的数据。

        原有 capture() 面向 JSON API，只返回元数据；3D 料架定位需要 numpy
        深度图/点云数据和原始文件路径，因此提供这个服务层内部接口。
        """
        if not self.is_streaming:
            raise DMCameraException("数据流未开启")

        frame_type_map = {
            'DEPTH': LWFrameType.LW_DEPTH_FRAME,
            'IR': LWFrameType.LW_IR_FRAME,
            'POINTCLOUD': LWFrameType.LW_POINTCLOUD_FRAME,
        }
        lw_frame_type = frame_type_map.get(frame_type, LWFrameType.LW_DEPTH_FRAME)
        frame_data = self._camera.capture_frame(lw_frame_type)
        result = {
            'frame_type': frame_type,
            'data': frame_data.data,
            'width': frame_data.width,
            'height': frame_data.height,
            'image_width': frame_data.width,
            'image_height': frame_data.height,
            'frame_index': frame_data.frameIndex,
            'confidence': 0.95,
            'raw_data_path': '',
            'result_image_path': '',
            'timestamp': {
                'sec': frame_data.timestamp.sec,
                'usec': frame_data.timestamp.usec,
            },
        }
        if save_record and self._current_session:
            record = self._save_capture_record(frame_data, frame_type)
            result['record_id'] = record.id
            result['raw_data_path'] = record.data_file.name if record.data_file else ''
            result['preview_url'] = record.preview_image.url if record.preview_image else ''
            result['result_image_path'] = record.preview_image.name if record.preview_image else ''
        return result

    def _save_capture_record(self, frame_data, frame_type: str) -> DMCaptureRecord:
        """保存采集记录"""
        config = self._current_session.config if self._current_session else None
        
        # 创建记录
        record = DMCaptureRecord.objects.create(
            config=config,
            frame_type=frame_type,
            frame_index=frame_data.frameIndex,
            width=frame_data.width,
            height=frame_data.height,
            temperature_chip=frame_data.temperature.chip if frame_data.temperature else None,
            temperature_laser1=frame_data.temperature.laser1 if frame_data.temperature else None,
            temperature_laser2=frame_data.temperature.laser2 if frame_data.temperature else None,
            metadata={
                'timestamp': {
                    'sec': frame_data.timestamp.sec,
                    'usec': frame_data.timestamp.usec
                }
            }
        )
        
        # 生成预览图
        if frame_type in ['DEPTH', 'IR']:
            preview_image = self._generate_preview_image(frame_data.data)
            if preview_image:
                # 保存预览图
                img_io = io.BytesIO()
                preview_image.save(img_io, format='PNG')
                img_io.seek(0)
                
                filename = f"{frame_type}_{frame_data.frameIndex}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                record.preview_image.save(filename, ContentFile(img_io.read()), save=True)
        
        # 保存原始数据，供 3D 料架定位算法追溯或离线复算。
        try:
            if getattr(frame_data, 'data', None) is not None:
                raw_io = io.BytesIO()
                np.save(raw_io, frame_data.data)
                raw_io.seek(0)
                filename = f"{frame_type}_{frame_data.frameIndex}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.npy"
                record.data_file.save(filename, ContentFile(raw_io.read()), save=True)
        except Exception as e:
            logger.error(f"保存原始帧数据失败: {str(e)}")

        return record
    
    def _generate_preview_image(self, data: np.ndarray) -> Optional[Image.Image]:
        """生成预览图像"""
        try:
            # 归一化到0-255
            data_normalized = ((data - data.min()) / (data.max() - data.min()) * 255).astype(np.uint8)
            
            # 转换为PIL Image
            image = Image.fromarray(data_normalized)
            return image
        except Exception as e:
            logger.error(f"生成预览图失败: {str(e)}")
            return None
    
    def get_status(self) -> Dict:
        """获取当前状态"""
        status = {
            'connected': self.is_connected,
            'streaming': self.is_streaming,
            'session': None,
            'device_info': None
        }
        
        if self._current_session:
            status['session'] = {
                'id': self._current_session.id,
                'device_sn': self._current_session.device_sn,
                'device_ip': self._current_session.device_ip,
                'status': self._current_session.status,
                'config_name': self._current_session.config.name if self._current_session.config else None
            }
        
        if self.is_connected and self._camera:
            try:
                status['device_info'] = self._camera.get_device_info_dict()
            except Exception as e:
                logger.error(f"获取设备信息失败: {str(e)}")
        
        return status
