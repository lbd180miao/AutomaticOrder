# Hik Camera Adapter Design

## Goal

Integrate the `Hik_camera` Python binding into the Django project through the existing device adapter layer, with a minimal capture API that can be tested without real hardware.

## Architecture

`apps.devices.adapters.camera.CameraAdapter` owns all direct interaction with `chg_hik`. The adapter reads `AUTOMATIC_ORDER["HIK_CAMERA"]` from Django settings, creates the output directory, opens the camera in IP-direct mode when both `CAMERA_IP` and `PC_IP` are configured, and otherwise uses the SDK enumeration mode.

The adapter imports `chg_hik` lazily inside `capture()` so Django can still start on development machines where the vendor SDK or Python extension is not installed.

## Behavior

`CameraAdapter.capture(camera_code, task_type)` returns:

```python
{
    "success": True,
    "image_path": "<captured file path>",
    "camera_code": "<input camera code>",
    "task_type": "<input task type>",
}
```

If `chg_hik` is unavailable, it raises `RuntimeError` with installation guidance. If the SDK raises during open or capture, that exception is wrapped in `RuntimeError` with camera context.

## Configuration

The default settings block is:

```python
"HIK_CAMERA": {
    "OUTPUT_DIR": BASE_DIR / "media" / "hik_captures",
    "CAMERA_IP": "",
    "PC_IP": "",
    "FORMAT": "PNG",
    "QUALITY": 5,
}
```

Empty IP settings use automatic camera enumeration. Providing both IP values uses IP-direct mode.

## Testing

Unit tests inject a fake `chg_hik` module into `sys.modules`, so the tests verify Django integration behavior without requiring MVS SDK, a camera, or the compiled extension.
