import importlib
import json
import os
import sys
import time
import uuid
from ctypes import POINTER, byref, cast, memset, sizeof
from pathlib import Path


def _prepare_runtime(sdk_lib_dir):
    if not sdk_lib_dir:
        return

    # Windows add_dll_directory 接受正斜杠或反斜杠，无需规范化
    os.environ['HCMVS_LIB'] = sdk_lib_dir
    path_parts = os.environ.get('PATH', '').split(os.pathsep)
    if sdk_lib_dir not in path_parts:
        os.environ['PATH'] = os.pathsep.join([sdk_lib_dir, *path_parts])

    if hasattr(os, 'add_dll_directory'):
        try:
            os.add_dll_directory(sdk_lib_dir)
        except (OSError, FileNotFoundError) as exc:
            raise RuntimeError(
                f'SDK目录无效: {sdk_lib_dir}\n'
                f'错误: {exc}\n'
                '请检查 SDK_LIB_DIR 配置是否正确'
            ) from exc


def _add_project_venv_site_packages(base_dir):
    python_version = f'python{sys.version_info.major}.{sys.version_info.minor}'
    venv_dir = Path(base_dir) / '.venv'
    candidates = [
        venv_dir / 'Lib' / 'site-packages',
        venv_dir / 'lib' / python_version / 'site-packages',
    ]
    for candidate in candidates:
        if candidate.exists():
            candidate_path = str(candidate)
            if candidate_path not in sys.path:
                sys.path.insert(0, candidate_path)


def _latest_image_path(output_dir):
    image_suffixes = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}
    images = [
        path for path in Path(output_dir).iterdir()
        if path.is_file() and path.suffix.lower() in image_suffixes
    ]
    if not images:
        return None
    return str(max(images, key=lambda path: path.stat().st_mtime))


def _capture_with_legacy_api(chg_hik, payload):
    capture_images = getattr(chg_hik, 'capture_images', None)
    if not capture_images:
        return None

    output_dir = payload['output_dir']
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    before_latest = _latest_image_path(output_dir)
    result = capture_images(
        output_dir=output_dir,
        format=payload.get('format', 'PNG'),
        quality=payload.get('quality', 5),
        camera_ip=payload.get('camera_ip') or None,
        pc_ip=payload.get('pc_ip') or None,
    )

    if not result.get('success'):
        raise RuntimeError(result.get('message', 'capture_images failed'))

    latest = _latest_image_path(output_dir)
    if latest and latest != before_latest:
        return latest
    if latest and result.get('images_captured', 0) > 0:
        return latest
    raise RuntimeError('capture_images succeeded but no image file was found')


def _is_camera_busy_ret(ret: int) -> bool:
    """判断 MVS SDK 返回码是否为相机占用/访问拒绝类错误。"""
    # 统一转为无符号32位整数后比较
    unsigned = ret & 0xFFFFFFFF
    return unsigned in (
        0x80000203,   # MV_E_RESOURCE_BUSY
        0x80000206,   # MV_E_ACCESS_DENIED
        0x80000201,   # MV_E_HANDLE (handle invalid, may happen if previous session leaked)
    )


def _capture_with_official_mvs(payload, max_open_retries=3, open_retry_delay=1.0):
    """Capture one frame with Hikrobot's official Python wrapper.

    The bundled ``chg_hik`` 0.4.1 binding calls the older
    ``MV_CC_SaveImageToFileEx`` API with a structure layout that no longer
    matches the installed MVS 4.8 SDK.  Acquisition succeeds, but saving a
    BayerGR8 frame fails with MV_E_SUPPORT (0x80000002).  The current official
    wrapper uses ``MV_CC_SaveImageToFileEx2`` and handles this camera/SDK pair.
    """
    sample_root = os.environ.get('MVCAM_COMMON_RUNENV')
    if not sample_root:
        sample_root = r'C:\Program Files (x86)\MVS\Development'
    mv_import_dir = Path(sample_root) / 'Samples' / 'Python' / 'MvImport'
    if not mv_import_dir.exists():
        raise RuntimeError(f'MVS Python wrapper not found: {mv_import_dir}')
    mv_import_path = str(mv_import_dir)
    if mv_import_path not in sys.path:
        sys.path.insert(0, mv_import_path)

    mvs = importlib.import_module('MvCameraControl_class')
    output_dir = Path(payload['output_dir'])
    output_dir.mkdir(parents=True, exist_ok=True)

    image_format = str(payload.get('format', 'BMP')).upper()
    image_types = {
        'JPEG': (mvs.MV_Image_Jpeg, 'jpg'),
        'JPG': (mvs.MV_Image_Jpeg, 'jpg'),
        'BMP': (mvs.MV_Image_Bmp, 'bmp'),
        'TIFF': (mvs.MV_Image_Tif, 'tif'),
        'TIF': (mvs.MV_Image_Tif, 'tif'),
        'PNG': (mvs.MV_Image_Png, 'png'),
    }
    if image_format not in image_types:
        raise RuntimeError(f'Unsupported camera image format: {image_format}')
    image_type, extension = image_types[image_format]
    image_path = output_dir / f'preview_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.{extension}'

    cam = None
    frame = None
    grabbing = False
    opened = False
    handle_created = False
    initialized = False
    try:
        ret = mvs.MvCamera.MV_CC_Initialize()
        if ret != 0:
            raise RuntimeError(f'MVS initialize failed: 0x{ret & 0xffffffff:08x}')
        initialized = True

        devices = mvs.MV_CC_DEVICE_INFO_LIST()
        layer_types = (
            mvs.MV_GIGE_DEVICE | mvs.MV_USB_DEVICE |
            mvs.MV_GENTL_CAMERALINK_DEVICE | mvs.MV_GENTL_CXP_DEVICE |
            mvs.MV_GENTL_XOF_DEVICE
        )
        ret = mvs.MvCamera.MV_CC_EnumDevices(layer_types, devices)
        if ret != 0:
            raise RuntimeError(f'MVS enumerate devices failed: 0x{ret & 0xffffffff:08x}')
        if devices.nDeviceNum == 0:
            raise RuntimeError('No Hikrobot camera was found')

        requested_ip = payload.get('camera_ip')
        requested_serial = payload.get('camera_serial')
        selected = None
        for index in range(devices.nDeviceNum):
            info = cast(devices.pDeviceInfo[index], POINTER(mvs.MV_CC_DEVICE_INFO)).contents
            if requested_ip and info.nTLayerType in (mvs.MV_GIGE_DEVICE, mvs.MV_GENTL_GIGE_DEVICE):
                value = info.SpecialInfo.stGigEInfo.nCurrentIp
                current_ip = '.'.join(str((value >> shift) & 0xff) for shift in (24, 16, 8, 0))
                if current_ip != requested_ip:
                    continue
            if requested_serial:
                serial_bytes = b''
                if info.nTLayerType in (mvs.MV_GIGE_DEVICE, mvs.MV_GENTL_GIGE_DEVICE):
                    serial_bytes = bytes(info.SpecialInfo.stGigEInfo.chSerialNumber)
                elif info.nTLayerType == mvs.MV_USB_DEVICE:
                    serial_bytes = bytes(info.SpecialInfo.stUsb3VInfo.chSerialNumber)
                serial = serial_bytes.split(b'\0', 1)[0].decode('ascii', errors='replace')
                if serial != requested_serial:
                    continue
            selected = info
            break
        if selected is None:
            identity = requested_serial or requested_ip or '(first available device)'
            raise RuntimeError(f'Hikrobot camera {identity} was not found')

        cam = mvs.MvCamera()
        ret = cam.MV_CC_CreateHandle(selected)
        if ret != 0:
            raise RuntimeError(f'MVS create handle failed: 0x{ret & 0xffffffff:08x}')
        handle_created = True

        # ── 打开相机（带重试，应对短暂占用 0x80000203）─────────────────────
        last_open_ret = None
        for open_attempt in range(max_open_retries):
            ret = cam.MV_CC_OpenDevice(mvs.MV_ACCESS_Exclusive, 0)
            if ret == 0:
                opened = True
                break
            last_open_ret = ret
            if _is_camera_busy_ret(ret) and open_attempt < max_open_retries - 1:
                wait = open_retry_delay * (2 ** open_attempt)  # 指数退避：1s, 2s ...
                sys.stderr.write(
                    f'Warning: MVS open camera busy '
                    f'0x{ret & 0xffffffff:08x} '
                    f'(attempt {open_attempt + 1}/{max_open_retries}), '
                    f'retrying in {wait:.1f}s...\n'
                )
                time.sleep(wait)
            else:
                break  # 非占用类错误，不重试
        if not opened:
            raise RuntimeError(f'MVS open camera failed: 0x{last_open_ret & 0xffffffff:08x}')
        # ─────────────────────────────────────────────────────────────────────

        feature_file_value = payload.get('feature_file')
        if feature_file_value:
            feature_file = Path(feature_file_value).resolve()
            if feature_file.suffix.lower() != '.mfs' or not feature_file.is_file():
                raise RuntimeError(f'Invalid MVS feature file: {feature_file}')
            ret = cam.MV_CC_FeatureLoad(str(feature_file))
            if ret != 0:
                raise RuntimeError(
                    f'MVS feature load failed for {feature_file}: 0x{ret & 0xffffffff:08x}'
                )
        else:
            # Only apply defaults when no tuned feature file was supplied.
            # An .mfs file owns these values and must not be overwritten.
            if selected.nTLayerType in (mvs.MV_GIGE_DEVICE, mvs.MV_GENTL_GIGE_DEVICE):
                packet_size = cam.MV_CC_GetOptimalPacketSize()
                if int(packet_size) > 0:
                    cam.MV_CC_SetIntValue('GevSCPSPacketSize', packet_size)

            ret = cam.MV_CC_SetEnumValue('TriggerMode', mvs.MV_TRIGGER_MODE_OFF)
            if ret != 0:
                raise RuntimeError(f'MVS set continuous trigger mode failed: 0x{ret & 0xffffffff:08x}')
        ret = cam.MV_CC_StartGrabbing()
        if ret != 0:
            raise RuntimeError(f'MVS start grabbing failed: 0x{ret & 0xffffffff:08x}')
        grabbing = True

        frame = mvs.MV_FRAME_OUT()
        memset(byref(frame), 0, sizeof(frame))
        ret = cam.MV_CC_GetImageBuffer(frame, 10000)
        if ret != 0 or not frame.pBufAddr:
            raise RuntimeError(f'MVS get image buffer failed: 0x{ret & 0xffffffff:08x}')

        image = mvs.MV_CC_IMAGE()
        memset(byref(image), 0, sizeof(image))
        image.nWidth = frame.stFrameInfo.nExtendWidth or frame.stFrameInfo.nWidth
        image.nHeight = frame.stFrameInfo.nExtendHeight or frame.stFrameInfo.nHeight
        image.enPixelType = frame.stFrameInfo.enPixelType
        image.pImageBuf = frame.pBufAddr
        image.nImageBufSize = frame.stFrameInfo.nFrameLenEx or frame.stFrameInfo.nFrameLen
        image.nImageLen = image.nImageBufSize

        save = mvs.MV_CC_SAVE_IMAGE_PARAM()
        memset(byref(save), 0, sizeof(save))
        save.enImageType = image_type
        save.iMethodValue = 1
        save.nQuality = 95 if extension == 'jpg' else 0
        save.nEndian = 0
        ret = cam.MV_CC_SaveImageToFileEx2(image, save, str(image_path))
        if ret != 0:
            raise RuntimeError(f'MVS save image failed: 0x{ret & 0xffffffff:08x}')
        if not image_path.is_file() or image_path.stat().st_size == 0:
            raise RuntimeError(f'MVS reported success but image is missing: {image_path}')
        return str(image_path)
    finally:
        if cam is not None and frame is not None and getattr(frame, 'pBufAddr', None):
            cam.MV_CC_FreeImageBuffer(frame)
        if cam is not None and grabbing:
            cam.MV_CC_StopGrabbing()
        if cam is not None and opened:
            cam.MV_CC_CloseDevice()
        if cam is not None and handle_created:
            cam.MV_CC_DestroyHandle()
        if initialized:
            mvs.MvCamera.MV_CC_Finalize()


def capture(payload):
    base_dir = payload.get('base_dir') or Path.cwd()
    _add_project_venv_site_packages(base_dir)
    _prepare_runtime(payload.get('sdk_lib_dir') or '')

    # 确保输出目录存在且可写
    output_dir = Path(payload['output_dir'])
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        # 验证目录可写
        test_file = output_dir / '.write_test'
        test_file.touch()
        test_file.unlink()
    except PermissionError as exc:
        raise RuntimeError(
            f'输出目录权限不足 {output_dir}: 请检查目录权限'
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f'输出目录错误 {output_dir}: {exc}'
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f'输出目录不可写 {output_dir}: {exc}'
        ) from exc

    try:
        chg_hik = importlib.import_module('chg_hik')
    except ImportError as exc:
        raise RuntimeError(
            '无法导入 chg_hik 模块。请确保：\n'
            '1. 已安装海康威视 MVS SDK\n'
            '2. 已编译安装 chg_hik Python 绑定 (maturin develop --release)\n'
            '3. SDK 的 Env.json 路径配置正确'
        ) from exc

    # Prefer the compatibility API when present.  On the installed chg_hik
    # build it can acquire a frame but cannot save it; transparently fall back
    # to Hikrobot's current official Python wrapper in that case.
    # The compatibility binding cannot load GenApi .mfs files.  When one is
    # configured, always use the official MVS wrapper so all tuned parameters
    # are applied before acquisition starts.
    if payload.get('feature_file'):
        return _capture_with_official_mvs(payload)

    if getattr(chg_hik, 'capture_images', None):
        try:
            legacy_image_path = _capture_with_legacy_api(chg_hik, payload)
            if legacy_image_path:
                return legacy_image_path
        except Exception as legacy_exc:
            try:
                return _capture_with_official_mvs(payload)
            except Exception as official_exc:
                raise RuntimeError(
                    f'Camera capture failed with both SDK bindings. '
                    f'legacy={legacy_exc}; official={official_exc}'
                ) from official_exc

    camera_ip = payload.get('camera_ip') or None
    pc_ip = payload.get('pc_ip') or None

    camera = chg_hik.Camera(
        output_dir=payload['output_dir'],
        format=payload.get('format', 'PNG'),
        quality=payload.get('quality', 5),
    )
    image_path = None
    camera_opened = False

    try:
        if camera_ip and pc_ip:
            camera.open(camera_ip=camera_ip, pc_ip=pc_ip)
        else:
            camera.open()
        camera_opened = True
        image_path = camera.capture()
        return image_path
    except Exception as exc:
        error_msg = str(exc)
        if 'timeout' in error_msg.lower():
            raise RuntimeError(
                f'相机连接超时: {exc}\n'
                '请检查：\n'
                '1. 相机是否通电\n'
                '2. 网络连接是否正常\n'
                '3. IP地址配置是否正确'
            ) from exc
        elif 'not found' in error_msg.lower() or 'no device' in error_msg.lower():
            raise RuntimeError(
                f'未找到相机设备: {exc}\n'
                '请检查：\n'
                '1. 相机是否已连接\n'
                '2. 相机驱动是否正确安装\n'
                '3. MVS SDK 是否正常工作'
            ) from exc
        else:
            raise RuntimeError(f'相机捕获失败: {exc}') from exc
    finally:
        # chg_hik 的一次性采集进程会在进程退出时释放相机。部分 MVS/SDK
        # 版本在 capture() 成功后再次调用 close_camera() 会触发二次释放，
        # 甚至让 worker 在写回成功结果前异常退出。采图成功时交给进程退出
        # 清理；仅在采图失败、worker 仍需继续执行时主动关闭。
        if camera_opened and not image_path:
            try:
                close_camera = getattr(camera, 'close_camera', None)
                if close_camera:
                    close_camera()
            except Exception:
                # 关闭失败不影响结果返回，但记录到stderr便于调试
                import sys
                sys.stderr.write(f'Warning: Failed to close camera\n')
                pass


def write_result(result_path, result):
    tmp_path = result_path.with_suffix(result_path.suffix + '.tmp')
    tmp_path.write_text(json.dumps(result), encoding='utf-8')
    tmp_path.replace(result_path)


def main():
    result_path = None
    image_path = None
    try:
        payload = json.loads(sys.argv[1])
        result_path = Path(payload['result_path'])
        image_path = capture(payload)
        # 捕获成功，写入结果
        write_result(result_path, {'success': True, 'image_path': image_path})
        return 0
    except BaseException as exc:  # noqa: BLE001
        # 只有真正的捕获失败才返回错误
        # 如果是关闭相机失败，检查是否已经有图像路径
        error_msg = str(exc)
        if 'Failed to close camera' in error_msg and image_path:
            # 相机关闭失败但拍照成功，返回成功
            write_result(result_path, {'success': True, 'image_path': image_path})
            return 0
        
        result = {'success': False, 'error': error_msg}
        if result_path:
            write_result(result_path, result)
        else:
            sys.stderr.write(json.dumps(result))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
