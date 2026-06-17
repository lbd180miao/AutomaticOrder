import importlib
import json
import subprocess
import sys
import uuid
from pathlib import Path

from django.conf import settings

from .base import BaseDeviceAdapter


class CameraAdapter(BaseDeviceAdapter):
    """Camera adapter backed by the Hikrobot ``chg_hik`` Python binding."""

    _dll_directory_handles = []

    def _prepare_runtime(self, sdk_lib_dir):
        """Expose the MVS runtime DLL directory to Python and Windows loader."""
        if not sdk_lib_dir:
            return

        import os

        os.environ['HCMVS_LIB'] = str(sdk_lib_dir)
        path_parts = os.environ.get('PATH', '').split(os.pathsep)
        if str(sdk_lib_dir) not in path_parts:
            os.environ['PATH'] = os.pathsep.join([str(sdk_lib_dir), *path_parts])

        if hasattr(os, 'add_dll_directory'):
            handle = os.add_dll_directory(str(sdk_lib_dir))
            self._dll_directory_handles.append(handle)

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

        try:
            with chg_hik.Camera(
                output_dir=output_dir.as_posix(),
                format=image_format,
                quality=quality,
            ) as camera:
                if camera_ip and pc_ip:
                    camera.open(camera_ip=camera_ip, pc_ip=pc_ip)
                else:
                    camera.open()
                return camera.capture()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f'Hik camera capture failed for {camera_code} ({task_type}): {exc}'
            ) from exc

    def capture(self, camera_code, task_type):
        """Trigger capture and return image path plus metadata."""
        hik_settings = getattr(settings, 'AUTOMATIC_ORDER', {}).get('HIK_CAMERA', {})
        output_dir = Path(hik_settings.get('OUTPUT_DIR', settings.MEDIA_ROOT / 'hik_captures')).resolve()
        camera_ip = hik_settings.get('CAMERA_IP') or None
        pc_ip = hik_settings.get('PC_IP') or None
        image_format = hik_settings.get('FORMAT', 'PNG')
        quality = hik_settings.get('QUALITY', 5)
        sdk_lib_dir = hik_settings.get('SDK_LIB_DIR')
        run_in_subprocess = hik_settings.get('RUN_IN_SUBPROCESS', True)

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
        except Exception as exc:
            raise RuntimeError(
                f'Hik camera output directory error for {camera_code} ({task_type}): '
                f'无法创建或写入目录 {output_dir}, 错误: {exc}'
            ) from exc

        if run_in_subprocess:
            image_path = self._capture_with_worker(
                output_dir,
                camera_ip,
                pc_ip,
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
