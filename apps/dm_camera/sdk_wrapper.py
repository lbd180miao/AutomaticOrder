"""
DM 3D深度相机SDK包装器
封装SDK调用，提供Python友好的接口
"""
import os
import sys
from pathlib import Path
from typing import Optional, Tuple, List
import numpy as np
from ctypes import c_uint64

# 使用项目内部的SDK文件
SDK_DIR = Path(__file__).parent / "sdk"
DLL_PATH = SDK_DIR / "lib" / "dm_c_sdk.dll"

# 动态添加SDK API路径
if str(SDK_DIR) not in sys.path:
    sys.path.insert(0, str(SDK_DIR))

# 导入SDK（从项目内部）
from LW_DM_Api import LWDM3DCamera, DeviceInfo, ParsingData, FilterParam
from LW_DM_Type import (
    LWReturnCode, LWSensorType, LWTriggerMode, 
    LWExposureMode, LWFrameType, LWDataRecvType
)


class DMCameraException(Exception):
    """DM相机异常"""
    pass


class DMCameraConfigurationError(DMCameraException):
    """DM相机配置无效，调用方不得回退到样例数据。"""


class DMCamera:
    """DM 3D深度相机包装类"""
    
    def __init__(self):
        """初始化相机SDK"""
        self.camera = None
        self.device_handle = None
        self.is_streaming = False
        self._init_sdk()
    
    def _init_sdk(self):
        """初始化SDK"""
        try:
            if not DLL_PATH.exists():
                raise DMCameraException(f"DLL文件不存在: {DLL_PATH}")
            
            self.camera = LWDM3DCamera(str(DLL_PATH))
        except Exception as e:
            raise DMCameraException(f"SDK初始化失败: {str(e)}")
    
    def find_devices(self) -> List[DeviceInfo]:
        """
        查找所有可用的DM相机设备
        
        Returns:
            设备信息列表
        """
        try:
            ret_code, device_list = self.camera.LWGetDeviceInfoList()
            if ret_code != LWReturnCode.LW_RETURN_OK.value:
                raise DMCameraException(f"查找设备失败，错误码: {ret_code}")
            
            return device_list
        except Exception as e:
            raise DMCameraException(f"查找设备异常: {str(e)}")
    
    def connect(self, device_info: Optional[DeviceInfo] = None) -> DeviceInfo:
        """
        连接到指定设备，如果未指定则连接到第一个设备
        
        Args:
            device_info: 设备信息，为None时自动连接第一个设备
            
        Returns:
            已连接的设备信息
        """
        try:
            # 如果没有指定设备，查找并连接第一个设备
            if device_info is None:
                devices = self.find_devices()
                if not devices:
                    raise DMCameraException("未找到可用设备")
                device_info = devices[0]
            
            # 打开设备
            ret_code = self.camera.LWOpenDevice(device_info.handle)
            if ret_code != LWReturnCode.LW_RETURN_OK.value:
                raise DMCameraException(f"打开设备失败，错误码: {ret_code}")
            
            self.device_handle = device_info.handle
            return device_info
        except Exception as e:
            raise DMCameraException(f"连接设备异常: {str(e)}")
    
    def disconnect(self):
        """断开设备连接"""
        try:
            if self.is_streaming:
                self.stop_stream()
            
            if self.device_handle is not None:
                ret_code = self.camera.LWCloseDevice(self.device_handle)
                if ret_code != LWReturnCode.LW_RETURN_OK.value:
                    raise DMCameraException(f"关闭设备失败，错误码: {ret_code}")
                
                self.device_handle = None
        except Exception as e:
            raise DMCameraException(f"断开设备异常: {str(e)}")
    
    def configure_camera(self, 
                        frame_rate: int = 10,
                        exposure_time: int = 1000,
                        trigger_mode: LWTriggerMode = LWTriggerMode.LW_TRIGGER_ACTIVE):
        """
        配置相机参数
        
        Args:
            frame_rate: 帧率
            exposure_time: 曝光时间（微秒）
            trigger_mode: 触发模式
        """
        if self.device_handle is None:
            raise DMCameraException("设备未连接")
        
        try:
            # 设置帧率
            ret = self.camera.LWSetFrameRate(self.device_handle, frame_rate)
            if ret != LWReturnCode.LW_RETURN_OK.value:
                raise DMCameraException(f"设置帧率失败，错误码: {ret}")
            
            # 设置触发模式
            ret = self.camera.LWSetTriggerMode(self.device_handle, trigger_mode)
            if ret != LWReturnCode.LW_RETURN_OK.value:
                raise DMCameraException(f"设置触发模式失败，错误码: {ret}")
            
            # 设置TOF曝光时间
            ret = self.camera.LWSetExposureTime(
                self.device_handle, 
                LWSensorType.LW_TOF_SENSOR, 
                [exposure_time]
            )
            if ret != LWReturnCode.LW_RETURN_OK.value:
                raise DMCameraException(f"设置曝光时间失败，错误码: {ret}")
            
        except Exception as e:
            raise DMCameraException(f"配置相机异常: {str(e)}")
    
    def set_filters(self, 
                   confidence: Tuple[bool, int] = (True, 15),
                   flying_pixels: Tuple[bool, int] = (True, 5),
                   spatial: Tuple[bool, int] = (True, 5)):
        """
        配置滤波器
        
        Args:
            confidence: 置信度滤波 (启用, 阈值)
            flying_pixels: 飞点滤波 (启用, 阈值)
            spatial: 空间滤波 (启用, 阈值)
        """
        if self.device_handle is None:
            raise DMCameraException("设备未连接")
        
        try:
            # 置信度滤波 - 确保阈值在合理范围内
            conf_enabled, conf_threshold = confidence
            if conf_enabled and conf_threshold < 1:
                conf_threshold = 15  # 使用默认值
            ret = self.camera.LWSetConfidenceFilterParams(
                self.device_handle, conf_enabled, conf_threshold
            )
            if ret != LWReturnCode.LW_RETURN_OK.value:
                raise DMCameraException(f"设置置信度滤波失败，错误码: {ret}")
            
            # 飞点滤波 - 确保阈值在合理范围内
            fly_enabled, fly_threshold = flying_pixels
            if fly_enabled and fly_threshold < 1:
                fly_threshold = 5  # 使用默认值
            ret = self.camera.LWSetFlyingPixelsFilterParams(
                self.device_handle, fly_enabled, fly_threshold
            )
            if ret != LWReturnCode.LW_RETURN_OK.value:
                raise DMCameraException(f"设置飞点滤波失败，错误码: {ret}")
            
            # 空间滤波 - SDK要求最小值为5，即使禁用也要传递有效参数
            spatial_enabled, spatial_threshold = spatial
            if spatial_threshold < 5:
                spatial_threshold = 5  # SDK最小值要求
            ret = self.camera.LWSetSpatialFilterParams(
                self.device_handle, spatial_enabled, spatial_threshold
            )
            if ret != LWReturnCode.LW_RETURN_OK.value:
                raise DMCameraException(f"设置空间滤波失败，错误码: {ret}")
            
        except Exception as e:
            raise DMCameraException(f"配置滤波器异常: {str(e)}")
    
    def start_stream(self, data_type: LWDataRecvType = LWDataRecvType.LW_DEPTH_IR_RTY):
        """
        开启数据流
        
        Args:
            data_type: 数据接收类型
        """
        if self.device_handle is None:
            raise DMCameraException("设备未连接")
        
        try:
            # 设置数据接收类型
            ret = self.camera.LWSetDataReceiveType(self.device_handle, data_type)
            if ret != LWReturnCode.LW_RETURN_OK.value:
                raise DMCameraException(f"设置数据类型失败，错误码: {ret}")
            
            # 开启数据流
            ret = self.camera.LWStartStream(self.device_handle)
            if ret != LWReturnCode.LW_RETURN_OK.value:
                raise DMCameraException(f"开启数据流失败，错误码: {ret}")
            
            self.is_streaming = True
        except Exception as e:
            raise DMCameraException(f"开启数据流异常: {str(e)}")
    
    def stop_stream(self):
        """停止数据流"""
        if self.device_handle is None:
            return
        
        try:
            ret = self.camera.LWStopStream(self.device_handle)
            if ret != LWReturnCode.LW_RETURN_OK.value:
                raise DMCameraException(f"停止数据流失败，错误码: {ret}")
            
            self.is_streaming = False
        except Exception as e:
            raise DMCameraException(f"停止数据流异常: {str(e)}")
    
    def capture_frame(self, frame_type: LWFrameType = LWFrameType.LW_DEPTH_FRAME) -> ParsingData:
        """
        捕获一帧数据
        
        Args:
            frame_type: 帧类型
            
        Returns:
            解析后的帧数据
        """
        if self.device_handle is None:
            raise DMCameraException("设备未连接")
        
        if not self.is_streaming:
            raise DMCameraException("数据流未开启")
        
        try:
            # 获取帧准备
            ret = self.camera.LWGetFrameReady(self.device_handle)
            if ret != LWReturnCode.LW_RETURN_OK.value:
                raise DMCameraException(f"获取帧准备失败，错误码: {ret}")
            
            # 获取帧数据
            ret, frame = self.camera.LWGetFrame(self.device_handle, frame_type)
            if ret != LWReturnCode.LW_RETURN_OK.value:
                raise DMCameraException(f"获取帧数据失败，错误码: {ret}")
            
            # 解析帧数据
            parsed_data = ParsingData(frame)
            return parsed_data
        except Exception as e:
            raise DMCameraException(f"捕获帧异常: {str(e)}")
    
    def get_device_info_dict(self) -> dict:
        """
        获取当前设备信息字典
        
        Returns:
            设备信息字典
        """
        if self.device_handle is None:
            raise DMCameraException("设备未连接")
        
        try:
            # 获取设备SN
            ret, sn = self.camera.LWGetDeviceSN(self.device_handle)
            
            # 获取帧率
            ret, frame_rate = self.camera.LWGetFrameRate(self.device_handle)
            
            # 获取触发模式
            ret, trigger_mode = self.camera.LWGetTriggerMode(self.device_handle)
            
            # 获取TOF分辨率
            ret, width, height = self.camera.LWGetResolution(
                self.device_handle, LWSensorType.LW_TOF_SENSOR
            )
            
            return {
                'sn': sn,
                'frame_rate': frame_rate,
                'trigger_mode': trigger_mode.name if hasattr(trigger_mode, 'name') else str(trigger_mode),
                'resolution': f"{width}x{height}",
                'is_streaming': self.is_streaming
            }
        except Exception as e:
            raise DMCameraException(f"获取设备信息异常: {str(e)}")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.disconnect()
