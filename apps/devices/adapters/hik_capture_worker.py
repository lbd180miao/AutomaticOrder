import importlib
import json
import os
import sys
from pathlib import Path


def _prepare_runtime(sdk_lib_dir):
    if not sdk_lib_dir:
        return

    os.environ['HCMVS_LIB'] = sdk_lib_dir
    path_parts = os.environ.get('PATH', '').split(os.pathsep)
    if sdk_lib_dir not in path_parts:
        os.environ['PATH'] = os.pathsep.join([sdk_lib_dir, *path_parts])

    if hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(sdk_lib_dir)


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
    except Exception as exc:
        raise RuntimeError(
            f'输出目录不可写 {output_dir}: {exc}'
        ) from exc

    chg_hik = importlib.import_module('chg_hik')
    legacy_image_path = _capture_with_legacy_api(chg_hik, payload)
    if legacy_image_path:
        return legacy_image_path

    camera_ip = payload.get('camera_ip') or None
    pc_ip = payload.get('pc_ip') or None

    camera = chg_hik.Camera(
        output_dir=payload['output_dir'],
        format=payload.get('format', 'PNG'),
        quality=payload.get('quality', 5),
    )
    image_path = None
    capture_error = None

    try:
        if camera_ip and pc_ip:
            camera.open(camera_ip=camera_ip, pc_ip=pc_ip)
        else:
            camera.open()
        image_path = camera.capture()
    except BaseException as exc:  # noqa: BLE001
        capture_error = exc
    finally:
        close_camera = getattr(camera, 'close_camera', None)
        if close_camera and image_path is None:
            try:
                close_camera()
            except BaseException as close_exc:  # noqa: BLE001
                if capture_error is None and image_path is None:
                    capture_error = close_exc

    if capture_error is not None:
        raise capture_error
    return image_path


def write_result(result_path, result):
    tmp_path = result_path.with_suffix(result_path.suffix + '.tmp')
    tmp_path.write_text(json.dumps(result), encoding='utf-8')
    tmp_path.replace(result_path)


def main():
    result_path = None
    try:
        payload = json.loads(sys.argv[1])
        result_path = Path(payload['result_path'])
        image_path = capture(payload)
    except BaseException as exc:  # noqa: BLE001
        result = {'success': False, 'error': str(exc)}
        if result_path:
            write_result(result_path, result)
        else:
            sys.stderr.write(json.dumps(result))
        return 1

    write_result(result_path, {'success': True, 'image_path': image_path})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
