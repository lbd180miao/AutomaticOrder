from LW_DM_Type import *
import platform
import numpy as np
from typing import Callable
from typing import Tuple
from typing import List


gCallbackFuncList = []
gUserDataList = []


def getStrFromBytes(arg:bytes) -> str:
    """
    将C语言字符串转换为Python字符串。

    Args:
        arg (bytes): C语言字符串(字节串)。

    Returns:
        str: (Python)字符串。
    """
    for encoding in ['utf-8', 'gbk', 'ascii', 'utf-16', 'gb2312', 'iso-8859-1', 'utf-32']:
        try:
            return arg.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None



class DeviceInfo:
    """
    设备信息结构体。
    """
    def __init__(self, arg:LWDeviceInfo):
        self.handle:int = arg.handle
        self.sn:str = arg.sn.decode('utf-8')
        self.type:str = arg.type.decode('utf-8')
        self.ip:str = arg.ip.decode('utf-8')
        self.local_ip:str = arg.local_ip.decode('utf-8')

    def __str__(self):
        return str("{{ {}: {}, {}: {}, {}: {}, {}: {}, {}: {} }}"
                   ).format("设备句柄", self.handle, "设备序列号", self.sn, "设备类型", self.type,
                            "设备IP地址", self.ip, "本地IP地址", self.local_ip)


class FilterParam:
    """
    滤波参数结构体。
    """
    def __init__(self, arg:LWFilterParam):
        self.enable:bool = arg.enable
        self.threshold:int = arg.threshold

    def __str__(self):
        return f'{{ 使能开关: {self.enable}, 阈值: {self.threshold} }}'
    

class TriggerFilterParam:
    """
    硬触发滤波参数结构体。
    """
    def __init__(self, arg1:int, arg2:int):
        self.duration:int = arg1
        self.interval:int = arg2

    def __str__(self):
        return f'{{ 信号持续时间: {self.duration}, 信号间隔时间: {self.interval} }}'


class TimeStamp:
    """
    时间戳结构体。
    """
    def __init__(self, arg:LWTimeStamp):
        self.sec:int = arg.tv_sec
        self.usec:int = arg.tv_usec

    def __str__(self):
        return f'{{ 秒: {self.sec}, 微秒: {self.usec} }}'


class Temperature:
    """
    温度结构体。
    """
    def __init__(self, arg:LWTemperature):
        self.laser1:float = round(arg.laser1, 1)
        self.laser2:float = round(arg.laser2, 1)
        self.chip:float = round(arg.chip, 1)

    def __str__(self):
        return f'{{ 激光器1: {self.laser1}℃, 激光器2: {self.laser2}℃, 芯片: {self.chip}℃ }}'


class NetworkInfo:
    """
    网络配置结构体。
    """
    def __init__(self, arg:LWNetworkInfo):
        self.type:int = int.from_bytes(arg.type, 'little')
        self.ip:str = arg.ip.decode('utf-8')
        self.netmask:str = arg.netmask.decode('utf-8')

    def __str__(self):
        val = '静态' if self.type > 0 else '动态'
        return f'{{ IPv4地址类型: {val}, IPv4地址: {self.ip}, 子网掩码: {self.netmask} }}'
    

class IntrinsicParam:
    """
    相机内参结构体。
    """
    def __init__(self, arg:LWSensorIntrinsicParam):
        self.fx:float = round(arg.fx, 6)
        self.fy:float = round(arg.fy, 6)
        self.cx:float = round(arg.cx, 6)
        self.cy:float = round(arg.cy, 6)
        self.k1:float = round(arg.k1, 6)
        self.k2:float = round(arg.k2, 6)
        self.k3:float = round(arg.k3, 6)
        self.p1:float = round(arg.p1, 6)
        self.p2:float = round(arg.p2, 6)

    def __str__(self):
        return str('{{ fx: {}, fy:{}, cx: {}, cy: {}, k1: {}, k2: {}, k3: {}, p1: {}, p2: {} }}' \
                   ).format(self.fx, self.fy, self.cx, self.cy, self.k1, self.k2, self.k3, self.p1, self.p2)


class ExtrinsicParam:
    """
    相机外参结构体。
    """
    def __init__(self, arg:LWSensorExtrinsicParam):
        self.rMatrix:List[float] = [[round(arg.rotation[0], 6), round(arg.rotation[1], 6), round(arg.rotation[2], 6)], \
                                    [round(arg.rotation[3], 6), round(arg.rotation[4], 6), round(arg.rotation[5], 6)], \
                                    [round(arg.rotation[6], 6), round(arg.rotation[7], 6), round(arg.rotation[8], 6)]]
        self.tMatrix:List[float] = [round(arg.translation[0], 6), round(arg.translation[1], 6), round(arg.translation[2], 6)]

    def __str__(self):
        return f'{{ 旋转矩阵: {self.rMatrix}, 平移矩阵: {self.tMatrix} }}'


class IMU:
    """
    IMU数据结构体。
    """
    def __init__(self, arg:LWIMUData):
        self.xAxisACC:float = round(arg.xAxisACC, 3)
        self.yAxisACC:float = round(arg.yAxisACC, 3)
        self.zAxisACC:float = round(arg.zAxisACC, 3)
        self.xAxisGyro:float = round(arg.xAxisGyro, 3)
        self.yAxisGyro:float = round(arg.yAxisGyro, 3)
        self.zAxisGyro:float = round(arg.zAxisGyro, 3)
        self.yawAngle:float = round(arg.yawAngle, 5)
        self.rollAngle:float = round(arg.rollAngle, 5)
        self.pitchAngle:float = round(arg.pitchAngle, 5)

    def __str__(self):
        return str('{{ ' \
        'x-轴向加速度(g*10^-3): {}, y-轴向加速度(g*10^-3): {}, z-轴向加速度(g*10^-3): {}, ' \
        'x-轴向角速度(mdps): {}, y-轴向角速度(mdps): {}, z-轴向上的角速度(mdps): {}, ' \
        '偏航角解算值(°): {}, 翻滚角解算值(°): {}, 俯仰角解算值(°): {} ' \
        '}}').format(self.xAxisACC, self.yAxisACC, self.zAxisACC, self.xAxisGyro, self.yAxisGyro, self.zAxisGyro, \
                     self.yawAngle, self.rollAngle, self.pitchAngle)


class Area:
    """
    用于表示识别出的托盘区域。
    """
    def __init__(self, arg:LWPalletAreaData):
        self.x:int = arg.x
        self.y:int = arg.y
        self.w:int = arg.w
        self.h:int = arg.h
        self.confidence:float = round(arg.conf, 2)

    def __str__(self):
        return f'{{左上角坐标: ({self.x}, {self.y}), 宽度: {self.w}, 高度: {self.h}, 置信度: {self.confidence}}}'


class PalletPose:
    """
    托盘位姿信息结构体。
    """
    def __init__(self, arg:LWPalletPoseData):
        self.x:float = round(arg.x, 4)
        self.y:float = round(arg.y, 4)
        self.z:float = round(arg.z, 4)
        self.rx:float = round(arg.rx, 2)
        self.ry:float = round(arg.ry, 2)
        self.rz:float = round(arg.rz, 2)
        self.cx:float = round(arg.cx, 2)
        self.cy:float = round(arg.cy, 2)
        self.area = Area(arg.box)

    def __str__(self):
        return str('{{' \
        '心点坐标: ({}, {}, {}), yoz面绕x轴偏转角: {}, yoz面绕y轴偏转角: {}, yoz面绕z轴偏转角: {}, ' \
        'IR图像上托盘中心像素坐标: ({}, {}), 托盘识别区域: {} ' \
        '}}').format(self.x, self.y, self.z, self.rx, self.ry, self.rz, self.cx, self.cy, self.area)


class Pallet:
    """
    托盘识别信息结构体。
    """
    def __init__(self, arg1:c_int32, arg2:c_int32, arg3:List[LWPalletPoseData]):
        self.identifyNumber:int = arg1
        self.errorCode:int = arg2
        self.poseData:List[PalletPose] = []
        for i in range(0, self.identifyNumber):
            self.poseData.append(PalletPose(arg3[i]))

    def __str__(self):
        # 将列表转换为字符串表示
        list_str = ', '.join(str(item) for item in self.poseData)
        return f'{{ 托盘识别数量: {self.identifyNumber}, 错误码: {self.errorCode}, 位姿数据: [ {list_str} ] }}'


class ParsingData:
    """
    帧数据解析后的结构体。
    """
    def __init__(self, frame:LWFrameData):
        self.width:int = frame.width
        self.height:int = frame.height
        self.frameIndex:int = frame.frameIndex
        self.timestamp = TimeStamp(frame.timestamp)
        self.temperature:Temperature = None
        self.imu:IMU = None
        self.pallet:Pallet = None
        if LWPixelFormat(frame.pixelFormat) is LWPixelFormat.LW_PIXEL_FORMAT_USHORT:
            self.data = np.ctypeslib.as_array(cast(frame.pFrameData, POINTER(c_uint16)), shape=(self.height, self.width))
        elif LWPixelFormat(frame.pixelFormat) is LWPixelFormat.LW_PIXEL_FORMAT_VECTOR3F:
            self.data = np.ctypeslib.as_array(cast(frame.pFrameData, POINTER(c_float)), shape=(self.height*self.width, 3))
        elif LWPixelFormat(frame.pixelFormat) is LWPixelFormat.LW_PIXEL_FORMAT_UCHAR:
            self.data = np.ctypeslib.as_array(cast(frame.pFrameData, POINTER(c_uint8)), shape=(self.height, self.width))
        elif LWPixelFormat(frame.pixelFormat) is LWPixelFormat.LW_PIXEL_FORMAT_RGB888:
            self.data = np.ctypeslib.as_array(cast(frame.pFrameData, POINTER(c_uint8)), shape=(self.height, self.width, 3))
            return
        # TOF自带数据
        self.temperature = Temperature(frame.temperature)
        self.imu = IMU(frame.pVariant.contents.imuData)
        # 托盘识别数据
        if frame.pVariant.contents.identifyEnable:
            self.pallet = Pallet(frame.pVariant.contents.identifyNumber, \
                                 frame.pVariant.contents.errorCode, \
                                 frame.pVariant.contents.poseData)

    def __str__(self):
        return str("{:<10}: {}\n{:<10}: {}\n{:<11}: {}\n{:<11}: {}\n{:<12}: {}\n{:<12}: {}\n{:<8}: {}\n{:<12}: ⬇\n{}\n"
                   ).format("像素宽度", self.width, "像素高度", self.height, "帧序号", self.frameIndex, \
                            "时间戳", self.timestamp, "温度", self.temperature, "IMU位姿", self.imu, \
                            "托盘识别信息", self.pallet, "数据", self.data)


class LWDM3DCamera:
    """
    用于管理3D相机的类。
    """
    def __init__(self, libname:str):
        self.dm_sdk = None
        system_ = platform.system().lower()
        machine_ = platform.machine().lower()
        if (system_ == 'windows' or system_ == 'linux') and (
                machine_ == 'amd64' or machine_ == 'x86_64' or machine_ == 'aarch64'):
            if (".dll" not in libname) and (system_ == 'windows'):
                raise Exception('Unable to load dynamic libraries for Windows.')
            if (".so" not in libname) and (system_ == 'linux'):
                raise Exception('Unable to load dynamic libraries for Linux.')
            self.dm_sdk = cdll.LoadLibrary(libname)
            self.dm_sdk.LWInitializeResources()
        else:
            raise Exception('do not supported OS', system_, machine_)

    def __del__(self):
        if self.dm_sdk is not None:
            self.dm_sdk.LWCleanupResources()

    def LWGetDeviceInfoList(self) -> Tuple[int, List[DeviceInfo]]:
        """
        获取所有可使用的设备信息列表。

        Returns:
            Tuple[int,List[DeviceInfo]]: 返回码和设备信息列表。
        """
        filledCount = c_int32()
        array_type = LWDeviceInfo * 255
        deviceInfoArr = array_type()
        ret = self.dm_sdk.LWGetDeviceInfoList(deviceInfoArr, 255, byref(filledCount))
        deviceInfoList = []
        for i in range(0, filledCount.value):
            deviceInfoList.append(DeviceInfo(deviceInfoArr[i]))
        return ret, deviceInfoList

    def LWFindDevices(self) -> Tuple[int, List[int]]:
        """
        查找所有可使用的设备。从当前版本开始, 不再建议使用该函数。请改用"LWGetDeviceInfoList"函数。

        Returns:
            Tuple[int,List[int]]: 返回码和设备描述符列表。
        """
        filledCount = c_int32()
        array_type = c_uint64 * 255
        handleListArr = array_type()
        ret = self.dm_sdk.LWFindDevices(handleListArr, 255, byref(filledCount))
        handleList = []
        for i in range(0, filledCount.value):
            handleList.append(handleListArr[i])
        return ret, handleList

    def LWOpenDevice(self, handle:int) -> int:
        """
        打开设备。
        
        Args:
            handle (int): 设备描述符。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWOpenDevice(c_uint64(handle))

    def LWCloseDevice(self, handle:int) -> int:
        """
        关闭设备。

        Args:
            handle (int): 设备描述符。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWCloseDevice(c_uint64(handle))

    def LWReconnectDevice(self, handle:int, timeout:int) -> int:
        """
        当出现网络异常断开时, 可调用此函数进行设备重连。

        Args:
            handle (int): 设备描述符。
            timeout (int): 重连超时时间, 单位: 毫秒。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWReconnectDevice(c_uint64(handle), c_uint32(timeout))

    def LWRebootDevice(self, handle:int) -> int:
        """
        设备将重启。设备重启后SDK不会重连设备, 需要使用者重新打开设备。

        Args:
            handle (int): 设备描述符。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWRebootDevice(c_uint64(handle))

    def LWSaveConfigureInfo(self, handle:int) -> int:
        """
        保存设备当前的各种配置参数(比如: 积分时间、触发模式、置信度滤波...), 下次打开设备时以此配置信息运行。

        Args:
            handle (int): 设备描述符。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSaveConfigureInfo(c_uint64(handle))

    def LWRemoveConfigureInfo(self, handle:int) -> int:
        """
        删除设备保存的配置参数。
        注: 设备会自动重启, 重新加载默认配置信息, 因此需要使用者重新打开设备。

        Args:
            handle (int): 设备描述符。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWRemoveConfigureInfo(c_uint64(handle))

    def LWRestoreFactoryConfigureInfo(self, handle:int) -> int:
        """
        恢复出厂设置, 与 "LWRemoveConfigureInfo" 函数相比只多了一项网络配置重置的额外操作。

        Args:
            handle (int): 设备描述符。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWRestoreFactoryConfigureInfo(c_uint64(handle))

    def LWStartStream(self, handle:int) -> int:
        """
        打开设备数据流。
        注: 在此之前请先设置好相应配置(比如: 各种滤波、触发模式、积分时间...), 否则为之前保存的各种配置参数。

        Args:
            handle (int): 设备描述符。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWStartStream(c_uint64(handle))

    def LWStopStream(self, handle:int) -> int:
        """
        关闭设备数据流。调用此函数之后便无法获取设备数据, 除非再次打开设备数据流。

        Args:
            handle (int): 设备描述符。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWStopStream(c_uint64(handle))

    def LWHasRgbModule(self, handle:int) -> Tuple[int, bool]:
        """
        查看设备是否具有RGB模块。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,bool]: 返回码和真值。
        """
        isHasRGB = c_bool()
        return self.dm_sdk.LWHasRgbModule(c_uint64(handle), byref(isHasRGB)), isHasRGB.value

    def LWSoftTrigger(self, handle:int) -> int:
        """
        在开启设备数据流之后, 每调用一次该函数时设备便发送一帧数据。
        注: 设备必须处于软触发模式。

        Args:
            handle (int): 设备描述符。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSoftTrigger(c_uint64(handle))

    def LWSetDataReceiveType(self, handle:int, type:LWDataRecvType) -> int:
        """
        设置数据接收类型。

        Args:
            handle (int): 设备描述符。
            type (LWDataRecvType): 数据接收类型。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetDataReceiveType(c_uint64(handle), type.value)

    def LWSetTimeout(self, handle:int, timeout:int) -> int:
        """
        设置各操作的执行超时时间。

        Args:
            handle (int): 设备描述符。
            timeout (int): 超时时间, 单位: 毫秒。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetTimeout(c_uint64(handle), c_uint32(timeout))

    def LWSetTriggerMode(self, handle:int, mode:LWTriggerMode) -> int:
        """
        设置设备的触发模式。

        Args:
            handle (int): 设备描述符。
            mode (LWTriggerMode): 触发模式。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetTriggerMode(c_uint64(handle), mode.value)

    def LWGetTriggerMode(self, handle:int) -> Tuple[int, LWTriggerMode]:
        """
        获取设备当前的触发模式。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,LWTriggerMode]: 返回码和触发模式。
        """
        mode = c_uint32()
        return self.dm_sdk.LWGetTriggerMode(c_uint64(handle), byref(mode)), LWTriggerMode(mode.value)

    def LWSetExposureMode(self, handle:int, sensor_type:LWSensorType, mode:LWExposureMode) -> int:
        """
        设置设备的曝光模式。

        Args:
            handle (int): 设备描述符。
            sensor_type (LWSensorType): 传感器类型(TOF/RGB)。
            mode (LWExposureMode): 曝光模式。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetExposureMode(c_uint64(handle), sensor_type.value, mode.value)

    def LWGetExposureMode(self, handle:int, sensor_type:LWSensorType) -> Tuple[int, LWExposureMode]:
        """
        获取设备当前的曝光模式。

        Args:
            handle (int): 设备描述符。
            sensor_type (LWSensorType): 传感器类型(TOF/RGB)。

        Returns:
            Tuple[int,LWExposureMode]: 返回码和曝光模式。
        """
        mode = c_uint32()
        return self.dm_sdk.LWGetExposureMode(c_uint64(handle), sensor_type.value, byref(mode)), LWExposureMode(mode.value)

    def LWSetHDRMode(self, handle:int, mode:LWHDRMode) -> int:
        """
        设置TOF传感器的HDR模式。请注意每种模式下的最大帧率(详见: "LWHDRMode" 枚举类型)。
        注: 必须在开启设备数据流之前进行设置, 以及设置相对应的曝光时间(详见: "LWHDRMode" 枚举类型)。

        Args:
            handle (int): 设备描述符。
            mode (LWHDRMode): HDR模式。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetHDRMode(c_uint64(handle), mode.value)

    def LWGetHDRMode(self, handle:int) -> Tuple[int, LWHDRMode]:
        """
        获取TOF传感器的HDR模式。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,LWHDRMode]: 返回码和HDR模式。
        """
        mode = c_uint32()
        return self.dm_sdk.LWGetHDRMode(c_uint64(handle), byref(mode)), LWHDRMode(mode.value)

    def LWSetTransformDepthToRgbEnable(self, handle:int, enabled:bool) -> int:
        """
        设置深度数据映射到RGB的使能开关。
        注: 映射后的深度图像的分辨率与RGB图像的分辨率相同。

        Args:
            handle (int): 设备描述符。
            enabled (bool): 使能开关。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetTransformDepthToRgbEnable(c_uint64(handle), c_bool(enabled))

    def LWSetTransformRgbToDepthEnable(self, handle:int, enabled:bool) -> int:
        """
        设置RGB数据映射到深度的使能开关。
        注: 映射后的RGB图像的分辨率与深度图像的分辨率相同。

        Args:
            handle (int): 设备描述符。
            enabled (bool): 使能开关。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetTransformRgbToDepthEnable(c_uint64(handle), c_bool(enabled))

    def LWSetFrameRate(self, handle:int, value:int) -> int:
        """
        设置数据的发送帧率。由于网络(带宽、丢包...)、设备性能(CPU、内存...)等因素导致实际帧率会略低于此设定值。
        注: 由于帧率与曝光时间呈负相关即曝光时间越大帧率就越低, 因此需要理清曝光时间与帧率的对应关系。

        Args:
            handle (int): 设备描述符。
            value (int): 帧率值。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetFrameRate(c_uint64(handle), c_int32(value))

    def LWGetFrameRate(self, handle:int) -> Tuple[int, int]:
        """
        获取设备当前的数据发送帧率。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,int]: 返回码和帧率。
        """
        value = c_int32()
        return self.dm_sdk.LWGetFrameRate(c_uint64(handle), byref(value)), value.value

    def LWSetExposureTime(self, handle:int, sensor_type:LWSensorType, et_array:List[int]) -> int:
        """
        设置设备的曝光时间。请注意每种HDR模式下的曝光时间设置个数(详见: "LWHDRMode”枚举类型" 枚举类型)。

        Args:
            handle (int): 设备描述符。
            sensor_type (LWSensorType): 传感器类型(TOF/RGB)。
            et_array (List[int]): 曝光时间。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        if not isinstance(et_array, list):
            print("et_array is not list!")
            return -1
        arrLen = len(et_array)
        arr_type = c_int32 * arrLen
        etArray = arr_type()
        i = 0
        for value in et_array:
            etArray[i] = value
            i += 1
        return self.dm_sdk.LWSetExposureTime(c_uint64(handle), sensor_type.value, etArray, arrLen)

    def LWGetExposureTime(self, handle:int, sensor_type:LWSensorType) -> Tuple[int, List[int]]:
        """
        获取设备的曝光时间。

        Args:
            handle (int): 设备描述符。
            sensor_type (LWSensorType): 传感器类型(TOF/RGB)。

        Returns:
            Tuple[int,List[int]]: 返回码和曝光时间。
        """
        filledCount = c_int32()
        arr_type = c_int32 * 10
        etArray = arr_type()
        ret = self.dm_sdk.LWGetExposureTime(c_uint64(handle), sensor_type.value, byref(etArray), 10, byref(filledCount))
        etList = []
        for i in range(0, filledCount.value):
            etList.append(etArray[i])
        return ret, etList

    def LWSetTimeFilterParams(self, handle:int, enable:bool, threshold:int=9) -> int:
        """
        设置时域均值滤波。

        Args:
            handle (int): 设备描述符。
            enable (bool): 使能开关。
            threshold (int, optional): 滤波阈值, 取值范围: [2, 28]。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        param = LWFilterParam(enable, threshold)
        return self.dm_sdk.LWSetTimeFilterParams(c_uint64(handle), param)

    def LWGetTimeFilterParams(self, handle:int) -> Tuple[int, FilterParam]:
        """
        获取时域均值滤波。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,FilterParam]: 返回码和滤波值。
        """
        param = LWFilterParam()
        return self.dm_sdk.LWGetTimeFilterParams(c_uint64(handle), byref(param)), FilterParam(param)
            

    def LWSetTimeMedianFilterParams(self, handle:int, enable:bool, threshold:int=5) -> int:
        """
        设置时域中值滤波。

        Args:
            handle (int): 设备描述符。
            enable (bool): 使能开关。
            threshold (int, optional): 滤波阈值, 取值范围: 3, 5, 7, 9。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        param = LWFilterParam(enable, threshold)
        return self.dm_sdk.LWSetTimeMedianFilterParams(c_uint64(handle), param)

    def LWGetTimeMedianFilterParams(self, handle:int) -> Tuple[int, FilterParam]:
        """
        获取时域中值滤波。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,FilterParam]: 返回码和滤波值。
        """
        param = LWFilterParam()
        return self.dm_sdk.LWGetTimeMedianFilterParams(c_uint64(handle), byref(param)), FilterParam(param)

    def LWSetSpatialFilterParams(self, handle:int, enable:bool, threshold:int=5) -> int:
        """
        设置空间滤波。

        Args:
            handle (int): 设备描述符。
            enable (bool): 使能开关。
            threshold (int, optional): 滤波阈值, 3, 5, 7。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        param = LWFilterParam(enable, threshold)
        return self.dm_sdk.LWSetSpatialFilterParams(c_uint64(handle), param)

    def LWGetSpatialFilterParams(self, handle:int) -> Tuple[int, FilterParam]:
        """
        获取空间滤波。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,FilterParam]: 返回码和滤波值。
        """
        param = LWFilterParam()
        return self.dm_sdk.LWGetSpatialFilterParams(c_uint64(handle), byref(param)), FilterParam(param)

    def LWSetFlyingPixelsFilterParams(self, handle:int, enable:bool, threshold:int=5) -> int:
        """
        设置飞点滤波。

        Args:
            handle (int): 设备描述符。
            enable (bool): 使能开关。
            threshold (int, optional): 滤波阈值, 取值范围: [1, 64]。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        param = LWFilterParam(enable, threshold)
        return self.dm_sdk.LWSetFlyingPixelsFilterParams(c_uint64(handle), param)

    def LWGetFlyingPixelsFilterParams(self, handle:int) -> Tuple[int, FilterParam]:
        """
        获取飞点滤波。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,FilterParam]: 返回码和滤波值。
        """
        param = LWFilterParam()
        return self.dm_sdk.LWGetFlyingPixelsFilterParams(c_uint64(handle), byref(param)), FilterParam(param)

    def LWSetConfidenceFilterParams(self, handle:int, enable:bool, threshold:int=15) -> int:
        """
        设置置信度滤波。

        Args:
            handle (int): 设备描述符。
            enable (bool): 使能开关。
            threshold (int, optional): 滤波阈值, 取值范围: [1, 150]。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        param = LWFilterParam(enable, threshold)
        return self.dm_sdk.LWSetConfidenceFilterParams(c_uint64(handle), param)

    def LWGetConfidenceFilterParams(self, handle:int) -> Tuple[int, FilterParam]:
        """
        获取置信度滤波。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,FilterParam]: 返回码和滤波值。
        """
        param = LWFilterParam()
        return self.dm_sdk.LWGetConfidenceFilterParams(c_uint64(handle), byref(param)), FilterParam(param)

    def LWSetIRGMMGain(self, handle:int, value:int) -> int:
        """
        设置IR伽马值。

        Args:
            handle (int): 设备描述符。
            value (int): 伽马值, 取值范围: [0, 255]。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetIRGMMGain(c_uint64(handle), c_uint32(value))

    def LWGetIRGMMGain(self, handle:int) -> Tuple[int, int]:
        """
        获取IR伽马值。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,int]: 返回码和伽马值。
        """
        value = c_int32()
        return self.dm_sdk.LWGetIRGMMGain(c_uint64(handle), byref(value)), value.value

    def LWSetRgbSensorGain(self, handle:int, value:int) -> int:
        """
        设置RGB传感器的增益值。

        Args:
            handle (int): 设备描述符。
            value (int): 增益值, 取值范围: [16, 988]。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetRgbSensorGain(c_uint64(handle), c_int32(value))

    def LWGetRgbSensorGain(self, handle:int) -> Tuple[int, int]:
        """
        获取RGB传感器的增益值。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,int]: 返回码和增益值。
        """
        val = c_int32()
        return self.dm_sdk.LWGetRgbSensorGain(c_uint64(handle), byref(val)), val.value

    def LWSetRgbSensorGamma(self, handle:int, value:int) -> int:
        """
        设置RGB传感器的伽马值。

        Args:
            handle (int): 设备描述符。
            value (int): 伽马值, 取值范围: [64, 300]。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetRgbSensorGamma(c_uint64(handle), c_int32(value))

    def LWGetRgbSensorGamma(self, handle:int) -> Tuple[int, int]:
        """
        获取RGB传感器的伽马值。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,int]: 返回码和伽马值。
        """
        val = c_int32()
        return self.dm_sdk.LWGetRgbSensorGamma(c_uint64(handle), byref(val)), val.value

    def LWSetRgbSensorBrightness(self, handle:int, value:int) -> int:
        """
        设置RGB传感器的亮度值。

        Args:
            handle (int): 设备描述符。
            value (int): 亮度值, 取值范围: [-64, 64]。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetRgbSensorBrightness(c_uint64(handle), c_int32(value))

    def LWGetRgbSensorBrightness(self, handle:int) -> Tuple[int, int]:
        """
        获取RGB传感器的亮度值。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,int]: 返回码和亮度值。
        """
        val = c_int32()
        return self.dm_sdk.LWGetRgbSensorBrightness(c_uint64(handle), byref(val)), val.value

    def LWSetRgbSensorContrastRatio(self, handle:int, value:int) -> int:
        """
        设置RGB传感器的对比度。

        Args:
            handle (int): 设备描述符。
            value (int): 对比度, 取值范围: [0, 95]。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetRgbSensorContrastRatio(c_uint64(handle), c_int32(value))

    def LWGetRgbSensorContrastRatio(self, handle:int) -> Tuple[int, int]:
        """
        获取RGB传感器的对比度。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,int]: 返回码和对比度。
        """
        val = c_int32()
        return self.dm_sdk.LWGetRgbSensorContrastRatio(c_uint64(handle), byref(val)), val.value

    def LWSetNetworkInfo(self, handle:int, type:int, ip:str, netmask:str='255.255.255.0') -> int:
        """
        设置设备的网络配置信息。

        Args:
            handle (int): 设备描述符。
            type (int): IPv4地址的类型, 0表示为动态IP地址, 1表示为静态IP地址。
            ip (str): IPv4地址。
            netmask (str): 子网掩码。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        info = LWNetworkInfo(type.to_bytes(1), ip.encode('utf-8'), netmask.encode('utf-8'))
        return self.dm_sdk.LWSetNetworkInfo(c_uint64(handle), info)

    def LWGetNetworkInfo(self, handle:int) -> Tuple[int, NetworkInfo]:
        """
        获取设备当前的网络配置信息。
        注: IPv4的地址类型, 其值为0时表示动态IP地址, 为1时表示静态IP地址。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,NetworkInfo]: 返回码和网络配置信息。
        """
        info = LWNetworkInfo()
        return self.dm_sdk.LWGetNetworkInfo(c_uint64(handle), byref(info)), NetworkInfo(info)

    def LWSetDeviceNumber(self, handle:int, value:int) -> int:
        """
        设置设备编号。

        Args:
            handle (int): 设备描述符。
            value (int): 编号, 取值范围: [1, 255]。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetDeviceNumber(c_uint64(handle), c_int32(value))

    def LWGetDeviceNumber(self, handle:int) -> Tuple[int, int]:
        """
        获取设备当前的编号。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,int]: 返回码和设备编号。
        """
        val = c_int32()
        return self.dm_sdk.LWGetDeviceNumber(c_uint64(handle), byref(val)), val.value

    def LWSetDepthCompensateValue(self, handle:int, value:int) -> int:
        """
        设置深度数据补偿值。

        Args:
            handle (int): 设备描述符。
            value (int): 补偿值, 取值范围: [0, 65535]。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetDepthCompensateValue(c_uint64(handle), c_int32(value))

    def LWGetDepthCompensateValue(self, handle:int) -> Tuple[int, int]:
        """
        设置设备当前的深度数据补偿值。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,int]: 返回码和深度补偿值。
        """
        val = c_int32()
        return self.dm_sdk.LWGetDepthCompensateValue(c_uint64(handle), byref(val)), val.value

    def LWSetHardTriggerFilterParams(self, handle:int, t1:int, t2:int) -> int:
        """
        设置硬件触发的滤波参数, 仅在触发模式为 "LW_TRIGGER_HARD_FILTER" 时生效。一个信号周期为: t1 / 1000 + t2, 单位: 毫秒。

        Args:
            handle (int): 设备描述符。
            t1 (int): 触发信号(电平信号)的持续时间。单位: 微秒, 取值范围: [1000, 65535]。
            t2 (int): 触发信号(电平信号)的间隔时间。单位: 毫秒, 取值范围: [50, 65535]。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetHardTriggerFilterParams(c_uint64(handle), c_int32(t1), c_int32(t2))

    def LWGetHardTriggerFilterParams(self, handle:int) -> Tuple[int, TriggerFilterParam]:
        """
        获取设备当前的硬触发滤波参数。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,TriggerFilterParam]: 返回码和滤波参数。
        """
        t1 = c_int32()
        t2 = c_int32()
        return self.dm_sdk.LWGetHardTriggerFilterParams(c_uint64(handle), byref(t1), byref(t2)), TriggerFilterParam(t1.value, t2.value)

    def LWSetResolution(self, handle:int, sensor_type:LWSensorType, width:int, height:int) -> int:
        """
        设置传感器的分辨率, 设置成功后将会断开与设备的连接，因此需要重新打开设备。。
        注: 目前仅支持TOF传感器的可设置组合为: 640*480、320*240、160*120; 支持RGB传感器的可设置组合为: 1600*1200、800*600、640*480。

        Args:
            handle (int): 设备描述符。
            sensor_type (LWSensorType): 传感器类型(TOF/RGB)。
            width (int): 宽度。
            height (int): 高度。
        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetResolution(c_uint64(handle), sensor_type.value, c_int32(width), c_int32(height))

    def LWGetResolution(self, handle:int, sensor_type:LWSensorType) -> Tuple[int, tuple]:
        """
        获取传感器的分辨率。

        Args:
            handle (int): 设备描述符。
            sensor_type (LWSensorType): 传感器类型(TOF/RGB)。

        Returns:
            Tuple[int,tuple]: 返回码和分辨率。
        """
        width = c_int32()
        height = c_int32()
        return self.dm_sdk.LWGetResolution(c_uint64(handle), sensor_type.value, byref(width), byref(height)), (width.value, height.value)

    def LWGetIntrinsicParam(self, handle:int, sensor_type:LWSensorType) -> Tuple[int, IntrinsicParam]:
        """
        获取传感器的内参。

        Args:
            handle (int): 设备描述符。
            sensor_type (LWSensorType): 传感器类型(TOF/RGB)。

        Returns:
            Tuple[int,IntrinsicParam]: 返回码和相机内参。
        """
        param = LWSensorIntrinsicParam()
        return self.dm_sdk.LWGetIntrinsicParam(c_uint64(handle), sensor_type.value, byref(param)), IntrinsicParam(param)

    def LWGetExtrinsicParam(self, handle:int, sensor_type:LWSensorType) -> Tuple[int, ExtrinsicParam]:
        """
        获取相机的外参。

        Args:
            handle (int): 设备描述符。
            sensor_type (LWSensorType): 已忽略。包含该参数只是为了与之前发布的版本兼容。

        Returns:
            Tuple[int,ExtrinsicParam]: 返回码和相机外参。
        """
        param = LWSensorExtrinsicParam()
        return self.dm_sdk.LWGetExtrinsicParam(c_uint64(handle), sensor_type.value, byref(param)), ExtrinsicParam(param)
            

    def LWGetIMUExtrinsicParam(self, handle:int) -> Tuple[int, List[float]]:
        """
        获取IMU传感器的外参(旋转矩阵)。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,List[float]]: 返回码和IMU外参。
        """
        param = LWIMUExtrinsicParam()
        return self.dm_sdk.LWGetIMUExtrinsicParam(c_uint64(handle), byref(param)), \
            [[round(param.rotation[0], 6), round(param.rotation[1], 6), round(param.rotation[2], 6)], \
             [round(param.rotation[3], 6), round(param.rotation[4], 6), round(param.rotation[5], 6)], \
             [round(param.rotation[6], 6), round(param.rotation[7], 6), round(param.rotation[8], 6)]]

    def LWGetIMUData(self, handle:int) -> Tuple[int, IMU]:
        """
        获取IMU传感器的位姿数据。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,IMU]: 返回码和位姿数据。
        """
        param = LWIMUData()
        return self.dm_sdk.LWGetIMUEData(c_uint64(handle), byref(param)), IMU(param)

    def LWGetDeviceSN(self, handle:int) -> Tuple[int, str]:
        """
        获取设备的SN号(产品序列号)。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,str]: 返回码和SN号。
        """
        arr_type = c_char * 16
        SN = arr_type()
        return self.dm_sdk.LWGetDeviceSN(c_uint64(handle), byref(SN), 16), getStrFromBytes(SN.value)

    def LWGetDeviceType(self, handle:int) -> Tuple[int, str]:
        """
        获取设备的类型。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,str]:返回码和设备型号。
        """
        arr_type = c_char * 16
        pType = arr_type()
        return self.dm_sdk.LWGetDeviceType(c_uint64(handle), byref(pType), 16), getStrFromBytes(pType.value)

    def LWGetTimeStamp(self, handle:int) -> Tuple[int, TimeStamp]:
        """
        获取设备当前的系统时间。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,TimeStamp]: 返回码和时间戳。
        """
        t = LWTimeStamp()
        return self.dm_sdk.LWGetTimeStamp(c_uint64(handle), byref(t)), TimeStamp(t)

    def LWGetSDKVersion(self) -> Tuple[int, str]:
        """
        获取当前SDK库的版本信息。

        Returns:
            Tuple[int,str]: 返回码和版本信息。
        """
        v = LWVersionInfo()
        return self.dm_sdk.LWGetLibVersion(byref(v)), str("{}.{}.{}.{}").format(v.major, v.minor, v.patch, v.reserved)

    def LWGetDeviceVersion(self, handle:int) -> Tuple[int, dict]:
        """
        获取设备的版本信息。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,dict]: 返回码和版本信息。
        """
        fv = LWVersionInfo()
        dv = LWVersionInfo()
        return self.dm_sdk.LWGetDeviceVersion(c_uint64(handle), byref(fv), byref(dv)), \
            {'固件版本':str("{}.{}.{}.{}").format(fv.major, fv.minor, fv.patch, fv.reserved), \
             '驱动版本':str("{}.{}.{}.{}").format(dv.major, dv.minor, dv.patch, dv.reserved)}

    def LWGetReturnCodeDescriptor(self, code:int) -> str:
        """
        获取返回码对应的描述信息。

        Args:
            code (int): 返回码。

        Returns:
            str: 返回码描述信息。
        """
        self.dm_sdk.LWGetReturnCodeDescriptor.restype = c_char_p
        return getStrFromBytes(self.dm_sdk.LWGetReturnCodeDescriptor(code))
 
    def LWGetFrameReady(self, handle:int) -> int:
        """
        从设备数据流里截取一帧数据, 以供 "LWGetFrame" 函数的后续处理。

        Args:
            handle (int): 设备描述符。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWGetFrameReady(c_uint64(handle))

    def LWGetFrame(self, handle:int, data_type:LWFrameType) -> Tuple[int, LWFrameData]:
        """
        获取指定类型的帧数据。
        注: 在调用此函数之前必须成功调用 "LWGetFrameReady" 函数。

        Args:
            handle (int): 设备描述符。
            data_type (LWFrameType): 要获取的帧类型。

        Returns:
            Tuple[int,LWFrameData]: 返回码和帧数据。
        """
        frame = LWFrameData()
        frame.frameType = LWFrameType.LW_TYPE_UNDEFINED.value
        return self.dm_sdk.LWGetFrame(c_uint64(handle), byref(frame), data_type.value), frame
    
    def LWGetDataFromFrame(self, frame:LWFrameData) -> ParsingData:
        """
        将 "LWFrameData" C结构体类型数据转换成python的(dict)内建类型数据。

        Args:
            frame (LWFrameData): 帧数据。

        Returns:
            ParsingData: 数据。
        """
        if LWFrameType(frame.frameType) is LWFrameType.LW_TYPE_UNDEFINED:
            return None
        return ParsingData(frame)

    def LWIMURotatePointCloud(self, frame:LWFrameData) -> Tuple[int, LWFrameData, List[float]]:
        """
        根据IMU的位姿信息进行点云旋转, 并输出旋转矩阵。
        注: "frame" 必须是从 "LWGetFrame" 函数中成功获取的数据帧。

        Args:
            frame (LWFrameData): 帧数据。

        Returns:
            Tuple[int,LWFrameData,List[float]]: 返回码、帧数据和旋转矩阵。
        """
        arr_type = c_float * 9
        pMatrix = arr_type()
        return self.dm_sdk.LWIMURotatePointCloud(byref(frame), byref(pMatrix)), \
            frame, \
            [[round(pMatrix[0], 6), round(pMatrix[1], 6), round(pMatrix[2], 6)], \
             [round(pMatrix[3], 6), round(pMatrix[4], 6), round(pMatrix[5], 6)], \
             [round(pMatrix[6], 6), round(pMatrix[7], 6), round(pMatrix[8], 6)]]

    def LWSavePointCloudAsPCDFile(self, filename:str, frame:LWFrameData, binary_mode:bool=False) -> int:
        """
        将点云数据保存为PCD文件格式。
        注: "frame" 必须是从 "LWGetFrame" 函数中成功获取的数据帧。

        Args:
            filename (str): 文件名, 比如: "D:/data/0001.pcd"。
            frame (LWFrameData): 帧数据。
            binary_mode (bool, optional): 值为 "true" 时, 将以二进制的形式存储, 反之以ASCII码的形式存储。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSavePointCloudAsPCDFile(c_char_p(filename.encode('utf-8')), byref(frame), c_bool(binary_mode))

    def LWSavePointCloudAsPLYFile(self, filename:str, frame:LWFrameData, binary_mode:bool=False) -> int:
        """
        将点云数据保存为PLY文件格式。
        注: "frame" 必须是从 "LWGetFrame" 函数中成功获取的数据帧。

        Args:
            filename (str): 文件名, 比如: "D:/data/0001.ply"。
            frame (LWFrameData): 帧数据。
            binary_mode (bool, optional): 值为 "true" 时, 将以二进制的形式存储, 反之以ASCII码的形式存储。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSavePointCloudAsPLYFile(c_char_p(filename.encode('utf-8')), byref(frame), c_bool(binary_mode))

    def LWSaveDataAsCSVFile(self, filename:str, frame:LWFrameData) -> int:
        """
        将数据帧保存为CSV文件格式。
        注: "frame" 必须是从 "LWGetFrame" 函数中成功获取的数据帧。

        Args:
            filename (str): 文件名, 比如: "D:/data/0001.csv"。
            frame (LWFrameData): 帧数据。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSaveDataAsCSVFile(c_char_p(filename.encode('utf-8')), byref(frame))

    def LWSaveRgbAsImageFile(self, filename:str, frame:LWFrameData) -> int:
        """
        将RGB数据保存为图像文件格式。
        注: "frame" 必须是从 "LWGetFrame" 函数中成功获取的数据帧。

        Args:
            filename (str): 文件名, 比如: "D:/data/0001.bmp"。
            frame (LWFrameData): 帧数据。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSaveRgbAsImageFile(c_char_p(filename.encode('utf-8')), byref(frame))
    
    def LWUpdateFirmware(self, handle:int, filename:str) -> int:
        """
        更新设备固件。
        注: 在更新成功后，会经过短暂的延时，然后设备将会重新启动；如果重启失败，设备须掉电重启，否则无法进行其它任何操作。

        Args:
            handle (int): 设备描述符。
            filename (str): 固件文件名(含路径)。
        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """        
        return self.dm_sdk.LWUpdateFirmware(c_uint64(handle), c_char_p(filename.encode('utf-8')))
    
    def LWUpdateFirmware1(self, deviceIP:str, filename:str) -> int:
        """
        更新设备固件(不需要打开设备)。
        注: 在更新成功后，会经过短暂的延时，然后设备将会重新启动；如果重启失败，设备须掉电重启，否则无法进行其它任何操作。

        Args:
            deviceIP (str): 设备IP。
            filename (str): 固件文件名(含路径)。
        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """        
        return self.dm_sdk.LWUpdateFirmware1(c_char_p(deviceIP.encode('utf-8')), c_char_p(filename.encode('utf-8')))
    
    def LWSetOutputDO(self, handle:int, channel:int, value:int) -> int:
        """
        设置数字输出(DO)的电平状态。

        Args:
            handle (int): 设备描述符。
            channel (int): 通道号, 从1开始, 1表示DO1、2则表示DO2, 以此类推。
            value (int): 电平状态, 1表示高电平, 0表示低电平。
        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """        
        return self.dm_sdk.LWSetOutputDO(c_uint64(handle), c_int32(channel), c_int32(value))
    
    def LWGetOutputDO(self, handle:int, channel:int) -> Tuple[int, int]:
        """
        获取数字输出(DO)的电平状态。

        Args:
            handle (int): 设备描述符。
            channel (int): 通道号, 从1开始, 1表示DO1、2则表示DO2, 以此类推。
        Returns:
            Tuple[int,int]: 返回码和电平状态, 1表示高电平, 0表示低电平。
        """        
        val = c_int32()
        return self.dm_sdk.LWGetOutputDO(c_uint64(handle), c_int32(channel), byref(val)), val.value

    def LWRegisterNetworkMonitoringCallback(self, callback:Callable[[int, str, object], None], userdata:c_void_p=c_void_p()) -> int:
        """
        注册网络异常检测的回调函数。当出现SDK与设备的网络连接异常时, 该回调函数会被立即调用。
        注: "userdata" 必须是c_void_p对象。

        Args:
            callback (Callable[[int, str, object], None]): 回调函数。
            userdata (c_void_p, optional): 用户数据, 默认为空。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        fty = CFUNCTYPE(None, c_uint64, c_char_p, c_void_p)
        gCallbackFuncList.insert(0, fty(callback))
        gUserDataList.insert(0, userdata)
        return self.dm_sdk.LWRegisterNetworkMonitoringCallback(gCallbackFuncList[0], gUserDataList[0])
    
    def LWRegisterNetworkMonitoringCallback1(self, handle:int, callback:Callable[[str, object], None], userdata:c_void_p=c_void_p()) -> int:
        """
        向特定设备注册网络异常检测的回调函数。当出现SDK与设备的网络连接异常时, 该回调函数会被立即调用。
        注: "userdata" 必须是c_void_p对象。优先级大于全局回调函数(即用LWRegisterNetworkMonitoringCallback函数注册的回调函数)。

        Args:
            handle (int): 设备描述符。
            callback (Callable[[str, object], None]): 回调函数。
            userdata (c_void_p, optional): 用户数据, 默认为空。
        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        fty = CFUNCTYPE(c_char_p, c_void_p)
        gCallbackFuncList.insert(2, fty(callback))
        gUserDataList.insert(2, userdata)
        return self.dm_sdk.LWRegisterNetworkMonitoringCallback1(c_uint64(handle), gCallbackFuncList[2], gUserDataList[2])

    def LWRegisterFrameReadyCallback(self, callback:Callable[[int, object], None], userdata:c_void_p=c_void_p()) -> int:
        """
        注册探测新数据可用的回调函数。每当有新数据可用时, 该回调函数会被立即调用。
        注: "userdata" 必须是c_void_p对象。

        Args:
            callback (Callable[[int, object], None]): 回调函数。
            userdata (c_void_p, optional): 用户数据, 默认为空。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        fty = CFUNCTYPE(None, c_uint64, c_void_p)
        gCallbackFuncList.insert(1, fty(callback))
        gUserDataList.insert(1, userdata)
        return self.dm_sdk.LWRegisterFrameReadyCallback(gCallbackFuncList[1], gUserDataList[1])
    
    def LWRegisterFrameReadyCallback1(self, handle:int, callback:Callable[[object], None], userdata:c_void_p=c_void_p()) -> int: 
        """
        向特定设备注册探测新数据可用的回调函数。每当有新数据可用时, 该回调函数会被立即调用。
        注: "userdata" 必须是c_void_p对象。优先级大于全局回调函数(即用LWRegisterFrameReadyCallback函数注册的回调函数)。

        Args:
            handle (int): 设备描述符。
            callback (Callable[[object], None]): 回调函数。
            userdata (c_void_p, optional): 用户数据, 默认为空。
        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型 
        """
        fty = CFUNCTYPE(c_void_p)
        gCallbackFuncList.insert(3, fty(callback))
        gUserDataList.insert(3, userdata)
        return self.dm_sdk.LWRegisterFrameReadyCallback1(c_uint64(handle), gCallbackFuncList[3], gUserDataList[3])
    

#************************************ 附加模块 --- 托盘识别 ************************************

    def LWHasPalletIdentifyModule(self, handle:int) -> Tuple[int, bool]:
        """
        用于判定当前设备是否支持托盘识别功能。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,bool]: 返回码和判定真值。
        """
        value = c_bool(False)
        return self.dm_sdk.LWHasPalletIdentifyModule(c_uint64(handle), byref(value)), value.value
    
    def LWUploadRKNNFile(self, handle:int, filename:str) -> int:
        """
        上传托盘识别的模型文件(.rknn格式文件)。

        Args:
            handle (int): 设备描述符。
            filename (str): 文件全名(含路径)。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWUploadRKNNFile(c_uint64(handle), c_char_p(filename.encode('utf-8')))
    
    def LWSetPalletConfigureFile(self, handle:int, filename:str) -> int:
        """
        设置与托盘识别相关的配置文件(内容为json格式)。

        Args:
            handle (int): 设备描述符。
            filename (str): 文件全名(含路径)。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetPalletConfigureFile(c_uint64(handle), c_char_p(filename.encode('utf-8')))

    def LWSetPalletConfigureFileFromBuffer(self, handle:int, content:str) -> int:
        """
        设置与托盘识别相关的配置信息(内容为json格式)。

        Args:
            handle (int): 设备描述符。
            content (str): 配置信息。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetPalletConfigureFileFromBuffer(c_uint64(handle), c_char_p(content.encode('utf-8')), len(content))
    
    def LWGetPalletConfigureFile(self, handle:int, filename:str) -> int:
        """
        获取与托盘识别相关的配置信息到指定文件(内容为json格式)。

        Args:
            handle (int): 设备描述符。
            filename (str): 文件全名(含路径)。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWGetPalletConfigureFile(c_uint64(handle), c_char_p(filename.encode('utf-8')))
    
    def LWGetPalletConfigureFileToBuffer(self, handle:int) -> Tuple[int, str]:
        """
        获取与托盘识别相关的配置信息。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,str]: 返回码和配置信息。
        """
        arr_type = c_char * 65535
        content = arr_type()
        return self.dm_sdk.LWGetPalletConfigureFileToBuffer(c_uint64(handle), byref(content), 65535), getStrFromBytes(content.value)

    def LWSetPalletIdentifyType(self, handle:int, type:str) -> int:
        """
        设置当前识别的托盘类型, 其值为配置文件里的第一层(最外层)的键。

        Args:
            handle (int): 设备描述符。
            type (str): 托盘类型。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetPalletIdentifyType(c_uint64(handle), c_char_p(type.encode('utf-8')))
    
    def LWGetPalletIdentifyType(self, handle:int) -> Tuple[int, str]:
        """
        获取当前识别的托盘类型。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,str]: 返回码和类型。
        """
        arr_type = c_char * 32
        type = arr_type()
        return self.dm_sdk.LWGetPalletIdentifyType(c_uint64(handle), byref(type), 32), getStrFromBytes(type.value)
    
    def LWSetPalletIdentifyEnable(self, handle:int, enable:bool) -> int:
        """
        设置托盘识别功能的使能开关。

        Args:
            handle (int): 设备描述符。
            enable (bool): 使能开关。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetPalletIdentifyEnable(c_uint64(handle), c_bool(enable))
    
    def LWGetPalletIdentifyEnable(self, handle:int) -> Tuple[int, bool]:
        """
        获取托盘识别功能的使能开关。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,bool]: 返回码和使能开关。
        """
        enable = c_bool()
        return self.dm_sdk.LWGetPalletIdentifyEnable(c_uint64(handle), byref(enable)), enable.value

    def LWSetTRSDsimilarMax(self, handle:int, value:float) -> int:
        """
        设置托盘识别的匹配相似度阈值。

        Args:
            handle (int): 设备描述符。
            value (float): 阈值, 取值范围: [0, 1], 默认值: 0.65。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetTRSDsimilarMax(c_uint64(handle), c_float(value))
    
    def LWGetTRSDsimilarMax(self, handle:int) -> Tuple[int, float]:
        """
        获取托盘识别的匹配相似度阈值。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,float]: 返回码和阈值。
        """
        value = c_float()
        return self.dm_sdk.LWGetTRSDsimilarMax(c_uint64(handle), byref(value)), round(value.value, 2)
    
    def LWSetTRSDpstMax(self, handle:int, value:float) -> int:
        """
        设置托盘识别的匹配重合度阈值。

        Args:
            handle (int): 设备描述符。
            value (float): 阈值, 取值范围: [0, 1], 默认值: 0.8。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetTRSDpstMax(c_uint64(handle), c_float(value))
    
    def LWGetTRSDpstMax(self, handle:int) -> Tuple[int, float]:
        """
        获取托盘识别的匹配重合度阈值。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,float]: 返回码和阈值。
        """
        value = c_float()
        return self.dm_sdk.LWGetTRSDpstMax(c_uint64(handle), byref(value)), round(value.value, 2)
    
    def LWSetCutHeight(self, handle:int, value:int) -> int:
        """
        设置托盘识别的截断高度。

        Args:
            handle (int): 设备描述符。
            value (int): 截断高度。

        Returns:
            int: 返回码, 详见: "LWReturnCode" 枚举类型。
        """
        return self.dm_sdk.LWSetCutHeight(c_uint64(handle), c_int32(value))
    
    def LWGetCutHeight(self, handle:int) -> Tuple[int, int]:
        """
        获取托盘识别的截断高度。

        Args:
            handle (int): 设备描述符。

        Returns:
            Tuple[int,int]: 返回码和截断高度。
        """
        value = c_int32()
        return self.dm_sdk.LWGetCutHeight(c_uint64(handle), byref(value)), value.value
