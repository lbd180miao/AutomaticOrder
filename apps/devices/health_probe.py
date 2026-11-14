"""Read-only probes, isolated from capture workers and bounded by the parent."""
import importlib
import os
import sys
from ctypes import POINTER, cast
from pathlib import Path


def probe(payload):
    if payload['kind'] == 'plc':
        return probe_plc(payload)

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


def probe_plc(payload):
    import socket
    from .adapters.plc import Snap7Transport, PLCAdapter
    from .plc_db100 import DB_NUMBER
    address = payload['address'].strip()
    connection = payload['connection']
    port = int(connection.get('tcp_port', 102))
    endpoint = f'{address}:{port}'
    try:
        with socket.create_connection((address, port), timeout=2) as sock:
            local_ip = sock.getsockname()[0]
    except OSError as exc:
        return {'state': 'offline', 'detail':
                f'TCP 端口不可达：{endpoint}。Ping 通仅说明 ICMP 有响应；请检查 PLC IP、TCP 端口、防火墙和网卡路由。原始错误：{exc}'}
    transport = Snap7Transport(address, **connection)
    try:
        try:
            if not transport.connect():
                raise ConnectionError('客户端未确认连接成功')
        except Exception as exc:
            return {'state': 'offline', 'detail':
                    f'TCP {endpoint} 可达（本机网卡 IP：{local_ip}），但 S7 建连失败。'
                    f'请核对 PLC 型号、Rack/Slot、S7 连接资源和访问设置。{exc}'}
        try:
            PLCAdapter(transport).read_listener_snapshot()
        except Exception as exc:
            return {'state': 'offline', 'detail':
                    f'S7 已连接（本机网卡 IP：{local_ip}），但 DB{DB_NUMBER} 五个监听地址读取失败，自动流程不可用。'
                    f'请核对 DB 编号、长度、访问权限及优化块设置。{exc}'}
        return {'state': 'online', 'detail':
                f'TCP / S7 / DB{DB_NUMBER} 五个监听地址读取均正常；本机网卡 IP：{local_ip}；'
                f'Rack={transport.rack}，Slot={transport.slot}。检测不写 PLC、不触发拍照。'}
    finally:
        try:
            transport.disconnect()
        except Exception:
            pass
