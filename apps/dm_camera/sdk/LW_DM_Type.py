from ctypes import *
from enum import Enum


class LWReturnCode(Enum):
    LW_RETURN_OK                    = 0x00 # 执行成功。
    LW_RETURN_COMMAND_UNDEFINED     = 0x03 # 命令未定义。
    LW_RETURN_COMMAND_ERROR         = 0x04 # 命令结构错误。
    LW_RETURN_ARG_OUT_OF_RANGE      = 0x05 # 参数设置超范围。
    LW_RETURN_FILE_LENGTH_ERROR     = 0x06 # 文件大小与实际传输大小不一致。
    LW_RETURN_FILE_MD5_ERROR        = 0x07 # 文件MD5校验失败。
    LW_RETURN_ACTION_INVALID        = 0x08 # 动作无效，已标定，请先取消标定再重新标定。
    LW_RETURN_REGION_INVALID        = 0x0b # 安防标定区域无效，其区域内有效点云数低于阈值，请重新选择更合适的区域。
    LW_RETURN_AJSON_FORMAT_ERROR    = 0x0c # 安防Json配置文件格式错误。
    LW_RETURN_AJSON_KEY_ERROR       = 0x0d # 安防Json配置文件键值类型/个数不符合。
    LW_RETURN_AJSON_VALUE_ERROR     = 0x0e # 安防Json配置文件键值超范围。
    LW_RETURN_AJSON_LOSS_ERROR      = 0x0f # 安防Json配置文件键值缺失。
    LW_RETURN_AJSON_PORJ_ERROR      = 0x10 # 安防Json配置文件项目名错误。
    LW_RETURN_AJSON_VERSION_ERROR   = 0x11 # 安防Json配置文件版本号与固件支持版本不匹配。
    LW_RETURN_AJSON_KEY_NAME_ERROR  = 0x12 # 安防Json配置文件键名错误。
    LW_RETURN_TIMEOUT               = 0x20 # 执行超时。
    LW_RETURN_NETWORK_ERROR         = 0x21 # 网络错误, 欲知详情请调用 "LWGetReturnCodeDescriptor" 函数。
    LW_RETURN_UNINITIALIZED         = 0x22 # SDK还未进行资源初始化(须调用 "LWInitializeResources" 函数来初始化资源)。
    LW_RETURN_UNOPENED              = 0x23 # 设备未打开(须调用 "LWOpenDevice" 函数来打开设备)。
    LW_RETURN_HANDLE_MISMATCH       = 0x24 # 传入的设备句柄无效, 请检查该句柄是否是 "LWFindDevices" 函数调用返回的设备句柄。
    LW_RETURN_FILE_OPEN_ERROR       = 0x25 # 文件打开失败。
    LW_RETURN_NOT_SUPPORTED         = 0x26 # 当前设备尚不支持该功能。
    LW_RETURN_VERSION_ERROR         = 0x27 # 协议版本不匹配。
    LW_RETURN_OUT_OF_MEMORY         = 0x28 # 传入的数据缓存大小不足。
    LW_RETURN_TYPE_NOT_EXIST        = 0x29 # 类型错误, 不存在该类型或是不支持该类型。
    LW_RETURN_TYPE_INPUT_ERROR      = 0x2a # 数据类型错误, 请传入正确类型的数据(例如: "LWSavePointCloudAsPCDFile" 函数只能传入点云数据)。
    LW_RETURN_THREAD_QUIT_TIMEOUT   = 0x2b # 线程退出超时。
    LW_RETURN_DATA_TYPE_MISMATCH    = 0x2c # 无法获取该类型数据, 请设置正确的数据接受类型。
    LW_RETURN_DATA_NOT_UPDATED      = 0x2d # 数据接受缓存区未更新数据, 在获取数据之前请先成功调用 "LWGetFrameReady" 函数。
    LW_RETURN_FILE_NOT_EXIST        = 0x2e # 文件不存在。
    LW_RETURN_DATA_SIZE_ERROR       = 0x2f # 传入的数据大小不匹配。
    LW_RETURN_FIRMWARE_UPDATE_FAIL  = 0x30 # 设备固件更新失败。
    LW_RETURN_INDEX_NOT_EXIST       = 0x31 # 不存在该索引值，请传入正确的索引值。
    LW_RETURN_DEVICE_INVALID        = 0x32 # SDK不支持该系列设备，请选择其对应的SDK进行相关操作。
    LW_RETURN_DEVICE_IP_CONFLICT    = 0x33 # 检测到接入的设备有相同的IP，导致无法访问有IP冲突的设备，须将每个设备的IP设置成唯一的。
    LW_RETURN_DEVICE_OCCUPIED       = 0x34 # 设备已被占用(设备已被其它设备描述符打开)。
    LW_RETURN_HANDLE_EXPIRE         = 0x35 # 设备描述符已失效，需要重新搜索设备获取新的设备描述符。
    LW_RETURN_CUSTOM_ERROR          = 0xfa # 自定义错误, 欲知详情请调用 "LWGetReturnCodeDescriptor" 函数。
    LW_RETURN_UNDEFINED_ERROR       = 0xff # 未定义错误。



class LWPalletErrorCode(Enum):
    LW_NO_ERROR             =  1 # 识别成功。
    LW_NOT_FOUND_ARG_SET    = -1 # 没有找到 "托盘算法参数集合名" 。
    LW_NOT_FOUND_MODEL      = -2 # 没有找到 "托盘算法模型" 。
    LW_NOT_FOUND_ARG_FILE   = -3 # 没有找到 "托盘算法参数集合名" 对应的json文件。
    LW_BUSY                 = -4 # 算法正在运行中,请稍后再试。
    LW_TIMEOUT              = -5 # 超时。
    LW_UNINITIALIZED        = -6 # 未完成初始化。
    LW_ARG_MISMATCH         = -7 # 参数不匹配。
    LW_ARG_REWORK           = -8 # 参数被修改, 当前识别结果不输出。
    LW_UNRECOGNIZED         = -9 # 模型未识别到托盘。


class LWFrameType(Enum):
    LW_TYPE_UNDEFINED       = 0B000000000 # 类型未定义。
    LW_DEPTH_FRAME          = 0B000000001 # 深度数据类型，单位：毫米。
    LW_AMPLITUDE_FRAME      = 0B000000010 # 幅度数据类型。
    LW_IR_FRAME             = 0B000000100 # IR数据类型。
    LW_POINTCLOUD_FRAME     = 0B000001000 # 点云数据类型，z-轴数据对应深度值。
    LW_RGB_FRAME            = 0B000010000 # RGB数据类型。
    LW_RGB_TO_DEPTH_FRAME   = 0B000100000 # RGB数据映射到深度后的RGB数据类型，其分辨率对齐到深度数据（与深度数据的分辨率一致）。
    LW_DEPTH_TO_RGB_FRAME   = 0B001000000 # 深度数据映射到RGB后的深度数据类型，其分辨率对齐到RGB数据（与RGB数据的分辨率一致）。
    LW_IR_TO_RGB_FRAME      = 0B100000000 # IR数据映射到RGB后的IR数据类型，其分辨率对齐到RGB数据（与RGB数据的分辨率一致）。
    LW_D2R_POINTCLOUD_FRAME = 0B010000000 # 深度数据映射到RGB后的点云数据类型，z-轴数据对应深度值，其点数对齐到RGB像素数（与RGB数据的像素数一致）。


class LWPixelFormat(Enum):
    LW_PIXEL_FORMAT_UCHAR       = 0x00 # 每像素为无符号字符型("unsigned char")。
    LW_PIXEL_FORMAT_USHORT      = 0x01 # 每像素为无符号短整型("unsigned short")。
    LW_PIXEL_FORMAT_RGB888      = 0x02 # 每像素为三通道无符号字符型(详见: "LWRGB888Pixel" 结构体)。
    LW_PIXEL_FORMAT_VECTOR3F    = 0x03 # 每像素为三通道浮点型(详见: "LWVector3f" 结构体)。


class LWDataRecvType(Enum):
    LW_IR_RTY                   = 0x04 # 设备只发送 "IR" 数据。
    LW_DEPTH_AMPLITUDE_RGB_RTY  = 0x05 # 设备只发送 "深度+幅度+RGB" 数据。由于点云数据是根据深度数据进行转换的, 因此亦可获取点云数据。
    LW_RGB_RTY                  = 0x06 # 设备只发送 "RGB" 数据。
    LW_DEPTH_IR_RTY             = 0x07 # 设备只发送 "深度+IR" 数据。由于点云数据是根据深度数据进行转换的, 因此亦可获取点云数据。
    LW_POINTCLOUD_IR_RTY        = 0x08 # 设备只发送 "点云+IR" 数据。
    LW_DEPTH_RGB_RTY            = 0x09 # 设备只发送 "深度+RGB" 数据。由于点云数据是根据深度数据进行转换的, 因此亦可获取点云数据。
    LW_DEPTH_IR_RGB_RTY         = 0x0C # 设备只发送“深度+IR+RGB”数据。由于点云数据是根据深度数据进行转换的，因此亦可获取点云数据。
    LW_POINTCLOUD_DEPTH_IR_RTY  = 0x0B # 设备只发送“点云+深度+IR”数据。特定版本---中日龙安防项目。


class LWSensorType(Enum):
    LW_TOF_SENSOR = 0x01 # TOF传感器。
    LW_RGB_SENSOR = 0x02 # RGB传感器。


class LWExposureMode(Enum):
    LW_EXPOSURE_AUTO    = 0x00 # 自动曝光, 由设备根据外部环境自行调整曝光时间。
    LW_EXPOSURE_MANUAL  = 0x01 # 手动曝光, 以设定的曝光时间为准, 不再进行自动调整。


class LWHDRMode(Enum):
    LW_DFN_NOT_HDR  = 0x00 # 适用于远距离且没有高动态范围的应用场景, 采用双频非HDR模式(双频2积分模式)。需设置1个曝光时间(例如:1000), 否则会使用默认的曝光时间。其帧率最高可达28帧。
    LW_SFN_HDR      = 0x01 # 适用于近距离且具有高动态范围的应用场景, 采用单频普通HDR模式(双频3积分模式)。需设置3个曝光时间依次对应高、中、低3个挡位(例如:1000, 150, 20), 否则会使用默认的曝光时间。其帧率最高可达18帧。
    LW_DFN_HDR      = 0x02 # 适用于远距离且具有高动态范围的应用场景, 采用双频普通HDR模式(双频6积分模式)。需设置3个曝光时间依次对应高、中、低3个挡位(例如:1000, 150, 20), 否则会使用默认的曝光时间。其帧率最高可达9帧。
    LW_SFN_HP_HDR   = 0x03 # 适用于近距离且具有高动态范围的静态应用场景, 采用单频高精度HDR模式(双频 6积分模式), 可提升距离探测精度。需设置3个曝光时间依次对应高、中、低3个挡位(例如:1000, 150, 20), 否则会使用默认的曝光时间。其帧率最高可达9帧。
    LW_DFN_HP_HDR   = 0x04 # 适用于远距离且具有高动态范围的静态应用场景, 采用双频高精度HDR模式(双频12积分模式), 可提升距离探测精度。需设置3个曝光时间依次对应高、中、低3个挡位(例如:1000, 150, 20), 否则会使用默认的曝光时间。其帧率最高可达5帧。
    LW_SFN_NOT_HDR  = 0xF1 # 适用于近距离且没有高动态范围的应用场景, 采用单频非HDR模式(单积分模式)。其帧率最高可达56帧。


class LWTriggerMode(Enum):
    LW_TRIGGER_ACTIVE       = 0x00 # 主动模式(连续触发)。当开启数据流时, 设备会按照指定帧率发送数据。
    LW_TRIGGER_SOFT         = 0x01 # 软触发模式。当开启数据流时, 每调用一次 "LWSoftTrigger" 函数设备便会发送一帧数据。建议将帧率设置为最大帧率, 至少不得低于触发的频率。
    LW_TRIGGER_HARD         = 0x02 # 硬触发模式。当开启数据流时, 设备每检测到一次外部信号(电平信号)便会发送一帧数据。建议将帧率设置为最大帧率, 至少不得低于触发的频率。
    LW_TRIGGER_HARD_FILTER  = 0x03 # 带滤波参数的硬触发模式(信号的持续时间和间隔)。根据设定的信号滤波参数, 设备每检测到一次外部信号(电平信号)便会发送一帧数据。建议将帧率设置为最大帧率, 至少不得低于触发的频率。



class LWDeviceInfo(Structure):
    _fields_ = [("handle", c_uint64),
                ("sn", c_char * 32),
                ("type", c_char * 32),
                ("ip", c_char * 32),
                ("local_ip", c_char * 32)]
    

class LWFilterParam(Structure):
    _fields_ = [("enable", c_bool),
                ("threshold", c_int32),
                ("k1", c_int32),
                ("k2", c_int32)]


class LWNetworkInfo(Structure):
    _fields_ = [("type", c_char),
                ("ip", c_char * 32),
                ("netmask", c_char * 32),
                ("gateway", c_char * 32),
                ("mac", c_char * 32),
                ("reserved", c_char * 96)]


class LWVersionInfo(Structure):
    _fields_ = [("major", c_int32),
                ("minor", c_int32),
                ("patch", c_int32),
                ("reserved", c_int32)]


class LWTemperature(Structure):
    _fields_ = [("laser1", c_float),
                ("laser2", c_float),
                ("chip", c_float)]


class LWTimeStamp(Structure):
    _fields_ = [("tv_sec", c_int64),
                ("tv_usec", c_int64)]


class LWSensorIntrinsicParam(Structure):
    _fields_ = [("fx", c_float),
                ("fy", c_float),
                ("cx", c_float),
                ("cy", c_float),
                ("k1", c_float),
                ("k2", c_float),
                ("k3", c_float),
                ("p1", c_float),
                ("p2", c_float)]


class LWSensorExtrinsicParam(Structure):
    _fields_ = [("rotation", c_float * 9),
                ("translation", c_float * 3)]


class LWIMUExtrinsicParam(Structure):
    _fields_ = [("rotation", c_float * 9)]


class LWIMUData(Structure):
    _fields_ = [("xAxisACC", c_float),
                ("yAxisACC", c_float),
                ("zAxisACC", c_float),
                ("xAxisGyro", c_float),
                ("yAxisGyro", c_float),
                ("zAxisGyro", c_float),
                ("yawAngle", c_float),
                ("rollAngle", c_float),
                ("pitchAngle", c_float)]


class LWPalletAreaData(Structure):
    _fields_ = [("x", c_int32),
                ("y", c_int32),
                ("w", c_int32),
                ("h", c_int32),
                ("conf", c_float)]


class LWPalletPoseData(Structure):
    _fields_ = [("x", c_float),
                ("y", c_float),
                ("z", c_float),
                ("rx", c_float),
                ("ry", c_float),
                ("rz", c_float),
                ("cx", c_float),
                ("cy", c_float),
                ("box", LWPalletAreaData)]


class LWVector3f(Structure):
    _fields_ = [("x", c_float),
                ("y", c_float),
                ("z", c_float)]


class LWRGB888Pixel(Structure):
    _fields_ = [("r", c_uint8),
                ("g", c_uint8),
                ("b", c_uint8)]


class LWVariant(Structure):
    _fields_ = [("calMode", c_int32),
                ("eParam", LWIMUExtrinsicParam),
                ("imuData", LWIMUData),
                ("identifyEnable", c_bool),
                ("identifyNumber", c_int32),
                ("errorCode", c_int32),
                ("poseData", LWPalletPoseData * 20)]


class LWFrameData(Structure):
    _fields_ = [("width", c_uint16),
                ("height", c_uint16),
                ("frameIndex", c_int32),
                ("bufferSize", c_int32),
                ("elemSize", c_uint32),
                ("total", c_int32),
                ("frameType", c_int32),
                ("pixelFormat", c_int32),
                ("temperature", LWTemperature),
                ("timestamp", LWTimeStamp),
                ("pFrameData", POINTER(c_uint8)),
                ("pVariant", POINTER(LWVariant))]

