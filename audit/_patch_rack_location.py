# -*- coding: utf-8 -*-
"""一次性补丁：把 rack_location.py 的 3D 相机源从 DM 切换为 RVC。"""
import io
import sys
from pathlib import Path

path = Path(r"D:\workspace2\AutomaticOrder\apps\vision\rack_location.py")
text = path.read_text(encoding="utf-8")

# 1) 增加 RVC 配置错误导入
old_imp = (
    "from apps.dm_camera.sdk_wrapper import DMCameraConfigurationError\n"
)
new_imp = (
    "from apps.dm_camera.sdk_wrapper import DMCameraConfigurationError\n"
    "from apps.rvc_camera.client import RvcCameraConfigurationError\n"
)
assert text.count(old_imp) == 1, "import anchor not found"
text = text.replace(old_imp, new_imp, 1)

# 2) 替换整个 DMCameraRackFrameProvider 类
start = text.index("class DMCameraRackFrameProvider:")
end = text.index("class PlcVisionResultWriter:")
old_class = text[start:end]

new_class = '''class RVCCameraRackFrameProvider:
    """Frame provider backed by the RVC 3D camera service, with sample fallback.

    现役 RVC 相机的 PyRVC 运行在独立进程 ``rvc_service`` 中（Django 只通过
    HTTP 调用）。RvcCameraService.capture_frame_data() 把点云放在 'data' 键，
    PointCloudProcessor.extract_pose() 使用 'organized_pointcloud' 或
    'pointcloud'，此处负责 key 映射（与旧 DM provider 行为一致）。
    """

    def __init__(self, *, fallback_provider: Optional[SampleRackFrameProvider] = None):
        self.fallback_provider = fallback_provider or SampleRackFrameProvider()

    def capture(self, recipe: RackLocationRecipe, position_no: int, layer_no: int) -> dict:
        if getattr(settings, 'VISION_RACK_LOCATION_FORCE_SAMPLE', False):
            frame = self.fallback_provider.capture(recipe, position_no, layer_no)
            frame['source'] = 'sample_forced'
            return frame

        try:
            from apps.rvc_camera.services import RvcCameraService

            service = RvcCameraService()
            if not service.is_connected:
                # 工作台采集不要求事先在相机页面手动连接：相机服务未连接时
                # 自动补连（IP/SN 取自 settings RVC_CAMERA），失败再回退模拟。
                service.ensure_connected()
            # RVC 为单次触发采集，无需 start_stream
            frame = service.capture_frame_data(frame_type='POINTCLOUD', save_record=False)

            # ── key 映射：服务层 'data' -> 算法层 'organized_pointcloud' ──
            result = {
                **frame,
                'source': 'rvc_camera',
                'position_no': position_no,
                'layer_no': layer_no,
            }
            raw_data = frame.get('data')
            if raw_data is not None:
                arr = np.asarray(raw_data)
                width = int(frame.get('width') or frame.get('image_width') or 0)
                height = int(frame.get('height') or frame.get('image_height') or 0)
                if arr.ndim == 3 and arr.shape[2] == 3:
                    # RVC 点云即 H×W×3 组织化点云
                    result['organized_pointcloud'] = arr
                elif arr.ndim == 2 and arr.shape[1] == 3:
                    if width > 0 and height > 0 and arr.shape[0] == width * height:
                        result['organized_pointcloud'] = arr.reshape(height, width, 3)
                    else:
                        result['pointcloud'] = arr
                elif arr.ndim == 1 and width > 0 and height > 0 and arr.size == width * height * 3:
                    result['organized_pointcloud'] = arr.reshape(height, width, 3)
                else:
                    result['pointcloud'] = arr
            return result
        except (DMCameraConfigurationError, RvcCameraConfigurationError):
            # 配置类错误（如不支持的采集模式）不得静默回退模拟数据
            raise
        except Exception as exc:  # noqa: BLE001 - hardware fallback is intentional
            frame = self.fallback_provider.capture(recipe, position_no, layer_no)
            frame['source'] = 'sample_fallback'
            frame['fallback_reason'] = str(exc)
            return frame


# 旧类名保留为别名，兼容既有测试与导入
DMCameraRackFrameProvider = RVCCameraRackFrameProvider


'''

text = text[:start] + new_class + text[end:]

# 3) 两处默认 source 名
n1 = text.count("frame.get('source', 'dm_camera')")
text = text.replace("frame.get('source', 'dm_camera')", "frame.get('source', 'rvc_camera')")
assert n1 == 2, f"expected 2 default-source sites, got {n1}"

# 4) 剩余两处 DMCameraConfigurationError 捕获改为同时捕获 RVC 配置错误
n2 = text.count("        except DMCameraConfigurationError:\n")
text = text.replace(
    "        except DMCameraConfigurationError:\n",
    "        except (DMCameraConfigurationError, RvcCameraConfigurationError):\n",
)
assert n2 == 2, f"expected 2 remaining catch sites, got {n2}"

# 5) fallback 原因展示条件同时识别两种真实相机源
old_cond = "if source != 'dm_camera' and fallback_reason:"
assert text.count(old_cond) == 1
text = text.replace(
    old_cond,
    "if source not in ('dm_camera', 'rvc_camera') and fallback_reason:",
)

path.write_text(text, encoding="utf-8")
print("rack_location.py patched OK")
