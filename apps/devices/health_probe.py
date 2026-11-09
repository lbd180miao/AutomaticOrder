"""Read-only probes, isolated from capture workers and bounded by the parent."""
import importlib
import os
import sys
from ctypes import POINTER, cast
from pathlib import Path


def probe(payload):
    if payload['kind'] == 'plc':
        from .adapters.plc import Snap7Transport
        transport = Snap7Transport(payload['address'], **payload['connection'])
        try:
            transport.connect()
            # An actual S7 response, not merely an open TCP port or cached flag.
            state = transport.client.get_cpu_state()
            return {'detail': f'S7 通信正常，CPU 状态：{state}'}
        finally:
            transport.disconnect()

    from .adapters.hik_capture_worker import _prepare_runtime
    _prepare_runtime(payload.get('sdk_lib_dir'))
    root = Path(os.environ.get('MVCAM_COMMON_RUNENV') or r'C:\Program Files (x86)\MVS\Development')
    wrapper = root / 'Samples' / 'Python' / 'MvImport'
    if not wrapper.is_dir():
        raise RuntimeError(f'MVS SDK Python 接口未安装：{wrapper}')
    sys.path.insert(0, str(wrapper))
    mvs = importlib.import_module('MvCameraControl_class')
    ret = mvs.MvCamera.MV_CC_Initialize()
    if ret:
        raise RuntimeError(f'MVS SDK 初始化失败：0x{ret & 0xffffffff:08x}')
    try:
        devices = mvs.MV_CC_DEVICE_INFO_LIST()
        ret = mvs.MvCamera.MV_CC_EnumDevices(mvs.MV_GIGE_DEVICE | mvs.MV_USB_DEVICE, devices)
        if ret:
            raise RuntimeError(f'MVS 设备发现失败：0x{ret & 0xffffffff:08x}')
        matches = []
        for i in range(devices.nDeviceNum):
            info = cast(devices.pDeviceInfo[i], POINTER(mvs.MV_CC_DEVICE_INFO)).contents
            ip = ''
            if info.nTLayerType == mvs.MV_GIGE_DEVICE:
                data = info.SpecialInfo.stGigEInfo
                ip = '.'.join(str((data.nCurrentIp >> s) & 255) for s in (24, 16, 8, 0))
            else:
                data = info.SpecialInfo.stUsb3VInfo
            serial = bytes(data.chSerialNumber).split(b'\0')[0].decode('ascii', errors='replace')
            if payload.get('serial') and serial != payload['serial']:
                continue
            if payload.get('address') and ip != payload['address']:
                continue
            matches.append((serial, ip))
        if not matches:
            raise RuntimeError('SDK 未发现目标相机。请检查供电、网线、网卡网段及配置的 IP/序列号；无法仅凭此结果确定断电或断线。')
        if len(matches) != 1:
            raise RuntimeError('发现多台相机，请配置唯一序列号或 IP')
        return {'detail': 'SDK 已发现目标相机（不打开设备、不触发采集；采集可用性需拍照验证）',
                'address': matches[0][1] or matches[0][0]}
    finally:
        mvs.MvCamera.MV_CC_Finalize()
