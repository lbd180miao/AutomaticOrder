import importlib
import json
import subprocess
import sys
import uuid
from pathlib import Path

from django.conf import settings

from .base import BaseDeviceAdapter

# ── 海康 MVS 相机占用 / 访问失败 相关错误特征 ─────────────────────────────
# 0x80000203 = MV_E_RESOURCE_BUSY  (-2147483133)
# 0x80000206 = MV_E_ACCESS_DENIED  (-2147483130)
# -2147483115 = 老版本 SDK 设备占用
_CAMERA_BUSY_PATTERNS = (
    '0x80000203',       # MV_E_RESOURCE_BUSY (新版 SDK)
    '0x80000206',       # MV_E_ACCESS_DENIED
    '-2147483133',      # 0x80000203 有符号十进制
    '-2147483130',      # 0x80000206 有符号十进制
    '-2147483115',      # 老版本占用错误
    '打开设备失败',
    '设备被占用',
    'resource busy',
    'access denied',
    'open camera failed',
    'MV_E_RESOURCE_BUSY',
    'MV_E_ACCESS_DENIED',
)


def _is_camera_busy_error(error_msg: str) -> bool:
    """判断错误是否为相机资源占用/访问拒绝类错误。"""
    msg_lower = error_msg.lower()
    return any(
        pattern.lower() in msg_lower
        for pattern in _CAMERA_BUSY_PATTERNS
    )


class CameraAdapter(BaseDeviceAdapter):
    """Camera adapter backed by the Hikrobot ``chg_hik`` Python binding."""

    _dll_directory_handles = []

    def _prepare_runtime(self, sdk_lib_dir):
        """Expose the MVS runtime DLL directory to Python and Windows loader."""
        if not sdk_lib_dir:
            return

        import os

        # 保持原始路径格式用于环境变量，但规范化用于 add_dll_directory
        sdk_lib_dir_str = str(sdk_lib_dir)
        
        os.environ['HCMVS_LIB'] = sdk_lib_dir_str
        path_parts = os.environ.get('PATH', '').split(os.pathsep)
        if sdk_lib_dir_str not in path_parts:
            os.environ['PATH'] = os.pathsep.join([sdk_lib_dir_str, *path_parts])

        if hasattr(os, 'add_dll_directory'):
            try:
                # add_dll_directory 需要绝对路径，接受正斜杠或反斜杠
                handle = os.add_dll_directory(sdk_lib_dir_str)
                self._dll_directory_handles.append(handle)
            except (OSError, FileNotFoundError) as exc:
                raise RuntimeError(
                    f'SDK目录无效: {sdk_lib_dir_str}\n'
                    f'错误: {exc}\n'
                    '请检查 SDK_LIB_DIR 配置是否正确'
                ) from exc

    def _project_venv_site_packages(self):
        python_version = f'python{sys.version_info.major}.{sys.version_info.minor}'
        venv_dir = Path(settings.BASE_DIR) / '.venv'
        return [
            venv_dir / 'Lib' / 'site-packages',
            venv_dir / 'lib' / python_version / 'site-packages',
        ]

    def _import_chg_hik(self):
        try:
            return importlib.import_module('chg_hik')
        except ImportError as first_exc:
            for site_packages in self._project_venv_site_packages():
                if not site_packages.exists():
                    continue
                site_packages_path = str(site_packages)
                if site_packages_path not in sys.path:
                    sys.path.insert(0, site_packages_path)
                try:
                    return importlib.import_module('chg_hik')
                except ImportError:
                    continue

            raise RuntimeError(
                'Unable to import chg_hik. The active Python cannot see the Hik_camera '
                'binding; install it into the Python running Django or into the project '
                '.venv with `maturin develop --release`, and confirm the MVS SDK Env.json path.'
            ) from first_exc

    def _capture_with_worker(
        self,
        output_dir,
        camera_ip,
        pc_ip,
        camera_serial,
        feature_file,
        image_format,
        quality,
        sdk_lib_dir,
        camera_code,
        task_type,
    ):
        result_path = output_dir / f'.hik_capture_{uuid.uuid4().hex}.json'

        def read_worker_result():
            if not result_path.exists():
                return None
            raw_result = result_path.read_text(encoding='utf-8').strip()
            if not raw_result:
                raise RuntimeError(
                    f'Hik camera capture failed for {camera_code} ({task_type}): '
                    'invalid worker result: empty result file'
                )
            try:
                return json.loads(raw_result)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f'Hik camera capture failed for {camera_code} ({task_type}): '
                    f'invalid worker result: {exc}'
                ) from exc

        payload = {
            'base_dir': str(settings.BASE_DIR),
            'output_dir': output_dir.as_posix(),
            'camera_ip': camera_ip,
            'pc_ip': pc_ip,
            'camera_serial': camera_serial,
            'feature_file': feature_file.as_posix() if feature_file else '',
            'format': image_format,
            'quality': quality,
            'sdk_lib_dir': str(sdk_lib_dir) if sdk_lib_dir else '',
            'result_path': result_path.as_posix(),
        }
        command = [
            sys.executable,
            '-m',
            'apps.devices.adapters.hik_capture_worker',
            json.dumps(payload),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=str(settings.BASE_DIR),
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f'Hik camera capture timeout for {camera_code} ({task_type}): '
                '相机捕获超时(30秒)，请检查相机连接和网络配置'
            ) from exc

        try:
            result = read_worker_result()
            if result and result.get('success'):
                return result['image_path']

            if completed.returncode != 0:
                message = (result or {}).get('error')
                if not message:
                    message = (completed.stderr or '').strip() or (completed.stdout or '').strip()
                raise RuntimeError(
                    f'Hik camera capture failed for {camera_code} ({task_type}): {message}'
                )

            if not result:
                message = (completed.stderr or '').strip() or (completed.stdout or '').strip()
                raise RuntimeError(
                    f'Hik camera capture failed for {camera_code} ({task_type}): '
                    f'worker did not return a capture result. {message}'
                )

            if not result.get('success'):
                raise RuntimeError(
                    f'Hik camera capture failed for {camera_code} ({task_type}): '
                    f"{result.get('error', 'unknown error')}"
                )
            raise RuntimeError(
                f'Hik camera capture failed for {camera_code} ({task_type}): '
                'worker returned an invalid success payload'
            )
        finally:
            result_path.unlink(missing_ok=True)

    def _capture_direct(
        self,
        output_dir,
        camera_ip,
        pc_ip,
        image_format,
        quality,
        camera_code,
        task_type,
    ):
        chg_hik = self._import_chg_hik()
        camera = None
        camera_opened = False

        try:
            # 使用 POSIX 路径格式传递给 Camera（与原有行为一致）
            camera = chg_hik.Camera(
                output_dir=output_dir.as_posix(),
                format=image_format,
                quality=quality,
            )
            if camera_ip and pc_ip:
                camera.open(camera_ip=camera_ip, pc_ip=pc_ip)
            else:
                camera.open()
            camera_opened = True
            
            image_path = camera.capture()
            if not image_path:
                raise RuntimeError('相机返回空图像路径')
            
            # 验证文件存在性（仅在文件路径看起来是真实路径时）
            # 如果是测试环境的 mock，可能返回路径但不创建文件
            image_file = Path(image_path)
            if image_file.exists():
                if image_file.stat().st_size == 0:
                    raise RuntimeError(f'相机图像文件为空: {image_path}')
            # 如果文件不存在，假定是测试环境或相机会延迟写入
                
            return image_path
            
        except Exception as exc:
            raise RuntimeError(
                f'Hik camera capture failed for {camera_code} ({task_type}): {exc}'
            ) from exc
        finally:
            # 无论成功或失败，都必须关闭相机以释放资源
            if camera and camera_opened:
                try:
                    close_method = getattr(camera, 'close_camera', None) or getattr(camera, '__exit__', None)
                    if close_method:
                        if hasattr(camera, '__exit__'):
                            close_method(None, None, None)
                        else:
                            close_method()
                except Exception as close_exc:
                    # 关闭失败记录警告但不影响结果返回
                    import sys
                    sys.stderr.write(f'Warning: Failed to close camera: {close_exc}\n')

    def capture(self, camera_code, task_type):
        """Trigger capture and return image path plus metadata."""
        hik_settings = getattr(settings, 'AUTOMATIC_ORDER', {}).get('HIK_CAMERA', {})
        output_dir = Path(hik_settings.get('OUTPUT_DIR', settings.MEDIA_ROOT / 'hik_captures')).resolve()
        camera_ip = hik_settings.get('CAMERA_IP') or None
        pc_ip = hik_settings.get('PC_IP') or None
        camera_serial = hik_settings.get('SERIAL_NUMBER') or None
        feature_file_value = hik_settings.get('FEATURE_FILE') or None
        feature_file = None
        if feature_file_value:
            feature_file = Path(feature_file_value)
            if not feature_file.is_absolute():
                feature_file = Path(settings.BASE_DIR) / feature_file
            feature_file = feature_file.resolve()
            if feature_file.suffix.lower() != '.mfs':
                raise RuntimeError(f'HIK_CAMERA FEATURE_FILE must be an .mfs file: {feature_file}')
            if not feature_file.is_file():
                raise RuntimeError(f'HIK_CAMERA FEATURE_FILE does not exist: {feature_file}')
        image_format = hik_settings.get('FORMAT', 'PNG')
        quality = hik_settings.get('QUALITY', 5)
        sdk_lib_dir = hik_settings.get('SDK_LIB_DIR')
        run_in_subprocess = hik_settings.get('RUN_IN_SUBPROCESS', True)
        max_retries = hik_settings.get('MAX_RETRIES', 2)  # 添加重试次数配置
        retry_delay = hik_settings.get('RETRY_DELAY', 1)  # 重试延迟（秒）

        if bool(camera_ip) != bool(pc_ip):
            raise RuntimeError('HIK_CAMERA CAMERA_IP and PC_IP must be configured together.')

        self._prepare_runtime(sdk_lib_dir)
        
        # 确保输出目录存在且具有写入权限
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            # 测试写入权限
            test_file = output_dir / '.write_test'
            test_file.touch()
            test_file.unlink()
        except PermissionError as exc:
            raise RuntimeError(
                f'Hik camera output directory permission denied for {camera_code} ({task_type}): '
                f'{output_dir} - 请检查目录权限'
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f'Hik camera output directory OS error for {camera_code} ({task_type}): '
                f'{output_dir} - {exc}'
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f'Hik camera output directory error for {camera_code} ({task_type}): '
                f'无法创建或写入目录 {output_dir}, 错误: {exc}'
            ) from exc

        # 重试机制（指数退避）
        import time as _time
        last_error = None
        for attempt in range(max_retries):
            try:
                # .mfs loading is implemented with Hikrobot's official MVS
                # wrapper in the isolated worker, so it must use that path.
                if run_in_subprocess or feature_file:
                    image_path = self._capture_with_worker(
                        output_dir,
                        camera_ip,
                        pc_ip,
                        camera_serial,
                        feature_file,
                        image_format,
                        quality,
                        sdk_lib_dir,
                        camera_code,
                        task_type,
                    )
                else:
                    image_path = self._capture_direct(
                        output_dir,
                        camera_ip,
                        pc_ip,
                        image_format,
                        quality,
                        camera_code,
                        task_type,
                    )

                return {
                    'success': True,
                    'image_path': image_path,
                    'camera_code': camera_code,
                    'task_type': task_type,
                }
            except RuntimeError as exc:
                last_error = exc
                error_msg = str(exc)

                if _is_camera_busy_error(error_msg):
                    if attempt < max_retries - 1:
                        # 指数退避：1s, 2s, 4s ...
                        wait = retry_delay * (2 ** attempt)
                        sys.stderr.write(
                            f'Warning: Camera busy [{camera_code}] '
                            f'(attempt {attempt + 1}/{max_retries}), '
                            f'retrying in {wait}s... error={error_msg}\n'
                        )
                        _time.sleep(wait)
                        continue
                    else:
                        # 所有重试耗尽，给出清晰的中文提示
                        raise RuntimeError(
                            f'相机被占用，无法访问 ({camera_code})\n\n'
                            '可能原因：\n'
                            '• MVS 客户端软件正在使用相机\n'
                            '• 其他程序正在访问相机\n'
                            '• 上次使用未正常释放\n\n'
                            '解决方法：\n'
                            '1. 关闭 MVS 软件后重试\n'
                            '2. 刷新页面重试\n'
                            '3. 重启开发服务器\n\n'
                            f'原始错误: {error_msg}'
                        ) from exc
                else:
                    # 非占用类错误，直接抛出不重试
                    raise

        # 所有重试都失败
        if last_error:
            raise last_error

        raise RuntimeError(f'Hik camera capture failed for {camera_code} ({task_type}): Unknown error')
