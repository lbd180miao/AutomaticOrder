"""料架定位算法（深度相机）。

用 OpenCV 生成模拟深度伪彩色图，以料架立柱为定位基准，计算装箱区域的
X/Y/Z 三轴补偿，并归档深度原图与带 ROI/补偿向量标注的结果图。
后期可在 locate() 内接入真实深度图/点云处理替换 generate/计算部分。
算法只输出结构化结果，不决定产线流程是否继续。
"""
from . import image_io


class RackLocator:
    """Depth-camera rack location with simulated depth scene and ROI annotation."""

    def __init__(self, *, simulate=True):
        self.simulate = simulate

    def locate(self, *, side, recipe=None, calibration_profile=None, image=None,
               simulated_offsets=None):
        """计算指定侧料架的 X/Y/Z 偏差与层高/层距实测值，并生成可视化图片。

        返回结构化字典，新增 original_image / result_image（media 相对路径）、
        pillar_roi / region_roi（ROI 坐标）。
        """
        if not self.simulate:
            raise NotImplementedError('真实深度相机定位算法尚未接入')

        defaults = {
            'LEFT': {'offset_x': 1.2, 'offset_y': -0.8, 'offset_z': 0.5},
            'RIGHT': {'offset_x': -1.0, 'offset_y': 0.6, 'offset_z': -0.4},
        }
        offsets = simulated_offsets or defaults.get(side, defaults['LEFT'])
        offsets = {
            'offset_x': round(float(offsets['offset_x']), 3),
            'offset_y': round(float(offsets['offset_y']), 3),
            'offset_z': round(float(offsets['offset_z']), 3),
        }

        if recipe is not None:
            measured_height = float(recipe.layer_height) + 0.5
            measured_spacing = float(recipe.layer_spacing) - 0.7
        else:
            measured_height = 120.5
            measured_spacing = 149.3

        # 1) 取得深度相机伪彩色画面（模拟）。
        depth_img, pillar, region = image_io.generate_depth_scene(side=side)

        # 2) 归档深度原图 + 带 ROI/补偿向量标注的结果图。
        original_path, w, h = image_io.save_image(depth_img, f'depth_{side.lower()}_raw')
        annotated = image_io.annotate_depth(depth_img, pillar, region, side, offsets)
        result_path, _, _ = image_io.save_image(
            annotated, f'depth_{side.lower()}_result', rel_dir='vision/results')

        return {
            'side': side,
            'offset_x': offsets['offset_x'],
            'offset_y': offsets['offset_y'],
            'offset_z': offsets['offset_z'],
            'measured_layer_height': round(measured_height, 3),
            'measured_layer_spacing': round(measured_spacing, 3),
            'confidence': 0.95,
            'is_success': True,
            'debug_image_path': result_path,
            'original_image': original_path,
            'result_image': result_path,
            'image_width': w,
            'image_height': h,
            'pillar_roi': pillar,
            'region_roi': region,
            'result_data': {
                'algorithm': 'simulated_rack_locator',
                'calibration': getattr(calibration_profile, 'version', None),
                'pillar_roi': pillar,
                'region_roi': region,
            },
        }
